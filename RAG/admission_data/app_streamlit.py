from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent
PIPELINE_DIR = ROOT / "pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))
ADVISOR_AVATAR = ROOT / "assets" / "advisor_avatar.svg"

from openai_rag_chat import DEFAULT_OPENAI_MODEL, call_openai_response
from advisor_common import SYSTEM_PROMPT, compact_contexts, load_local_env, sanitize_client_answer
from retrieve_context import retrieve_context


load_local_env()


TOPIC_OPTIONS = {
    "All topics": None,
    "Programs": "program",
    "Admissions pages": "admission_page",
    "School profiles": "school_page",
    "Scholarships": "scholarship",
    "Deadlines": "deadline",
    "Tuition": "tuition",
    "Requirements": "requirement",
    "University rankings": "university_ranking",
    "Country pathways": "country_advice",
    "Program pathways": "program_advice",
}
PROGRAM_LEVELS = {
    "Any level": None,
    "Undergraduate": "undergrad",
    "Master's": "master",
    "PhD": "phd",
    "Certificate": "certificate",
    "Unknown": "unknown",
}
EXAMPLE_PROMPTS = [
    "Which universities are strong for computer science and have scholarship options?",
    "What is a good study pathway for Germany international students?",
    "Which options are realistic for a student with IELTS 6.5?",
    "Compare tuition, English requirements, and application timeline for my options.",
]


def init_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_context" not in st.session_state:
        st.session_state.last_context = None
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None


def sidebar_options() -> dict:
    debug_enabled = os.getenv("ADVISOR_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    with st.sidebar:
        st.markdown("### Advisor Controls")
        topic_label = st.selectbox("Topic", list(TOPIC_OPTIONS), index=0)
        country = st.text_input("Country", placeholder="Germany, Canada, USA").strip()
        program_level_label = st.selectbox("Program level", list(PROGRAM_LEVELS), index=0)
        exclude_stale = st.checkbox("Use only current-cycle dates", value=False)
        show_context = False
        if debug_enabled:
            with st.expander("Private debug", expanded=True):
                show_context = st.checkbox("Show retrieved context", value=False)
                st.caption("Only enable for internal testing. Do not show during client demos.")

        if st.button("Start new conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.last_context = None
            st.session_state.pending_prompt = None
            st.rerun()

    return {
        "doc_type": TOPIC_OPTIONS[topic_label],
        "school_id": None,
        "country": country or None,
        "program_level": PROGRAM_LEVELS[program_level_label],
        "context_limit": int(os.getenv("RAG_CONTEXT_LIMIT", "4")),
        "context_chars": int(os.getenv("RAG_CONTEXT_CHARS", "4500")),
        "search_k": int(os.getenv("RAG_SEARCH_K", "500")),
        "exclude_stale": exclude_stale,
        "openai_model": os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        "max_output_tokens": int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "700")),
        "temperature": 0.2,
        "show_context": show_context,
    }


def make_retrieval_namespace(query: str, options: dict) -> argparse.Namespace:
    return argparse.Namespace(
        query=query,
        index=str(ROOT / "data" / "clean" / "rag" / "rag_openai_3_small.faiss"),
        metadata=str(ROOT / "data" / "clean" / "rag" / "rag_openai_3_small_metadata.jsonl"),
        docs=str(ROOT / "data" / "clean" / "rag" / "rag_documents_with_supplemental.jsonl"),
        model="text-embedding-3-small",
        dimensions=None,
        device="cpu",
        limit=options["context_limit"],
        search_k=options["search_k"],
        doc_type=options["doc_type"],
        school_id=options["school_id"],
        country=options["country"],
        program_level=options["program_level"],
        exclude_stale=options["exclude_stale"],
        pretty=False,
    )


def answer_question(query: str, options: dict) -> tuple[str, dict]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "The advisor is not connected yet. Add OPENAI_API_KEY to admission_data/.env, then restart the app.", {"query": query, "contexts": []}
    index_path = ROOT / "data" / "clean" / "rag" / "rag_openai_3_small.faiss"
    metadata_path = ROOT / "data" / "clean" / "rag" / "rag_openai_3_small_metadata.jsonl"
    if not index_path.exists() or not metadata_path.exists():
        return (
            "The advisor knowledge search is still being prepared. Build the OpenAI vector index first, then try again.",
            {"query": query, "contexts": []},
        )

    retrieval = retrieve_context(make_retrieval_namespace(query, options))
    context_text = compact_contexts(retrieval["contexts"], max_chars=options["context_chars"])
    if not context_text:
        context_text = "No verified private facts were found for this question. Provide general admissions guidance only."

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Private facts for internal use only:\n{context_text}\n\n"
                f"User question: {query}\n\n"
                "Answer from these facts first if they directly answer the question. Use natural, parent-and-student-friendly wording. If recommending schools or countries, prioritize options represented in the available school/program list. Use program/admission/school facts as the base, and use rankings only as reputation support. Create a balanced shortlist with safer, good-fit, and slightly challenging options when possible. Do not put schools in the main list if the student clearly misses a hard requirement. Keep the answer brief by default, usually under 180 words unless the user asks for detail. If the facts are missing or weak, give general expert guidance. Do not reveal or refer to the private facts, notes, source URLs, or scrape details."
            ),
        },
    ]
    try:
        answer = call_openai_response(
            model=options["openai_model"],
            instructions=SYSTEM_PROMPT,
            user_content=messages[-1]["content"],
            temperature=options["temperature"],
            max_output_tokens=options["max_output_tokens"],
        )
    except Exception as exc:
        return "The advisor is temporarily unavailable. Please try again in a moment.", retrieval
    return sanitize_client_answer(answer), retrieval


def apply_page_style() -> None:
    st.markdown(
        """
        <style>
            :root {
                --advisor-ink: #1f2937;
                --advisor-muted: #667085;
                --advisor-line: #d8dee8;
                --advisor-blue: #1d4ed8;
                --advisor-blue-soft: #eaf1ff;
                --advisor-green: #0f766e;
                --advisor-salmon: #e56b61;
                --advisor-salmon-dark: #cf5b52;
                --advisor-surface: #f7f9fc;
            }

            .main .block-container {
                max-width: 1120px;
                padding-top: 2rem;
                padding-bottom: 1.2rem;
            }

            h1, h2, h3, p {
                letter-spacing: 0;
            }

            [data-testid="stSidebar"] {
                background: #f6f8fb;
                border-right: 1px solid var(--advisor-line);
            }

            [data-testid="stToolbar"],
            [data-testid="stDecoration"] {
                display: none;
            }

            header[data-testid="stHeader"] {
                background: transparent;
            }

            .advisor-header {
                border-bottom: 1px solid var(--advisor-line);
                padding-bottom: 0.7rem;
                margin-bottom: 1rem;
            }

            .advisor-kicker {
                color: var(--advisor-salmon);
                font-size: 0.82rem;
                font-weight: 700;
                letter-spacing: 0;
                text-transform: uppercase;
                margin-bottom: 0.35rem;
            }

            .advisor-title {
                color: var(--advisor-ink);
                font-size: clamp(2rem, 5vw, 2.85rem);
                font-weight: 760;
                line-height: 1.05;
                margin: 0;
            }

            .advisor-subtitle {
                display: none;
            }

            .advisor-metrics {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.75rem;
                margin: 0.8rem 0 1.1rem;
            }

            .advisor-metric {
                border: 1px solid var(--advisor-line);
                border-radius: 8px;
                padding: 0.8rem 0.9rem;
                background: white;
            }

            .advisor-metric strong {
                color: var(--advisor-ink);
                display: block;
                font-size: 0.98rem;
                margin-bottom: 0.15rem;
            }

            .advisor-metric span {
                color: var(--advisor-muted);
                font-size: 0.86rem;
            }

            .prompt-label {
                color: var(--advisor-ink);
                font-weight: 700;
                margin: 0.5rem 0 0.55rem;
            }

            div[data-testid="stChatMessage"] {
                border-radius: 8px;
                border: 1px solid #e5eaf2;
                background: #ffffff;
            }

            div[data-testid="stChatMessage"] img {
                width: 32px;
                height: 32px;
                border-radius: 50%;
            }

            .advisor-input-panel {
                margin-top: 0;
                border: 1px solid var(--advisor-line);
                border-radius: 8px;
                background: #ffffff;
                padding: 0.75rem 1rem 0.45rem;
            }

            .advisor-chat-area {
                margin-top: 0.65rem;
            }

            .advisor-composer {
                position: sticky;
                bottom: 0;
                z-index: 10;
                background: rgba(255, 255, 255, 0.98);
                border-top: 1px solid var(--advisor-line);
                padding-top: 0.55rem;
                margin-top: 0.45rem;
            }

            .advisor-input-title {
                color: var(--advisor-ink);
                font-weight: 700;
                margin-bottom: 0.18rem;
            }

            .advisor-input-help {
                color: var(--advisor-muted);
                font-size: 0.9rem;
                margin-bottom: 0;
            }

            div[data-testid="stTextArea"] textarea {
                min-height: 118px;
                border-radius: 8px;
                line-height: 1.45;
            }

            div[data-testid="stTextArea"] {
                margin-top: -0.25rem;
            }

            div[data-testid="stForm"] {
                border: 1px solid var(--advisor-line);
                border-top: 0;
                border-radius: 0 0 8px 8px;
                padding: 0.85rem 1rem 1rem;
                margin-top: -0.2rem;
            }

            .advisor-input-panel + div[data-testid="stForm"] {
                border-top-left-radius: 0;
                border-top-right-radius: 0;
            }

            div[data-testid="stTextArea"] textarea:focus {
                border-color: var(--advisor-salmon);
                box-shadow: 0 0 0 1px var(--advisor-salmon);
                outline: none;
            }

            .stButton > button {
                border-radius: 8px;
                border: 1px solid var(--advisor-line);
                background: white;
                color: var(--advisor-ink);
                min-height: 3rem;
                white-space: normal;
                text-align: left;
            }

            .stButton > button:hover {
                border-color: var(--advisor-blue);
                color: var(--advisor-blue);
                background: var(--advisor-blue-soft);
            }

            .stButton > button:focus,
            .stButton > button:active {
                border-color: var(--advisor-line);
                color: var(--advisor-ink);
                background: white;
                box-shadow: none;
                outline: none;
            }

            div[data-testid="stFormSubmitButton"] button {
                border-radius: 8px;
                background: var(--advisor-salmon);
                border: 1px solid var(--advisor-salmon);
                color: white;
                min-height: 2.8rem;
                font-weight: 700;
            }

            div[data-testid="stFormSubmitButton"] button p {
                color: white;
            }

            div[data-testid="stFormSubmitButton"] button:hover {
                background: var(--advisor-salmon-dark);
                border-color: var(--advisor-salmon-dark);
                color: white;
            }

            div[data-testid="stFormSubmitButton"] button:hover p,
            div[data-testid="stFormSubmitButton"] button:focus p,
            div[data-testid="stFormSubmitButton"] button:active p {
                color: white;
            }

            div[data-testid="stFormSubmitButton"] button:focus,
            div[data-testid="stFormSubmitButton"] button:active {
                background: var(--advisor-salmon-dark);
                border-color: var(--advisor-salmon-dark);
                color: white;
                box-shadow: none;
                outline: none;
            }

            @media (max-width: 760px) {
                .advisor-metrics {
                    grid-template-columns: 1fr;
                }
                .main .block-container {
                    padding-left: 1rem;
                    padding-right: 1rem;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        """
        <section class="advisor-header">
            <div class="advisor-kicker">Admissions Advisor</div>
            <h1 class="advisor-title">Find the right school path with clearer evidence.</h1>
        </section>
        <section class="advisor-metrics">
            <div class="advisor-metric"><strong>Programs</strong><span>Compare fit, level, tuition, and requirements.</span></div>
            <div class="advisor-metric"><strong>Timelines</strong><span>Use estimated timelines when exact current dates need confirmation.</span></div>
            <div class="advisor-metric"><strong>Pathways</strong><span>Explore study, work, and immigration planning by country.</span></div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_prompt_buttons() -> None:
    if st.session_state.messages:
        return
    st.markdown('<div class="prompt-label">Common student questions</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for index, prompt in enumerate(EXAMPLE_PROMPTS):
        with cols[index % 2]:
            if st.button(prompt, key=f"prompt_{index}", use_container_width=True):
                st.session_state.pending_prompt = prompt
                st.rerun()


def handle_user_turn(user_input: str, options: dict) -> None:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant", avatar=str(ADVISOR_AVATAR)):
        with st.spinner("Preparing your answer..."):
            answer, retrieval = answer_question(user_input, options)
        st.markdown(answer)
        if options["show_context"] and retrieval.get("contexts"):
            render_debug_context(retrieval)
    st.session_state.messages.append({"role": "assistant", "content": answer, "retrieval": retrieval})
    st.session_state.last_context = retrieval


def render_debug_context(retrieval: dict) -> None:
    with st.expander("Retrieved context - private debug", expanded=False):
        for index, item in enumerate(retrieval.get("contexts", []), start=1):
            st.markdown(
                f"**{index}. {item.get('title', 'Untitled')}**  \n"
                f"Score: `{item.get('score')}` | Type: `{item.get('doc_type')}` | "
                f"School: `{item.get('school_name') or 'N/A'}` | Country: `{item.get('country') or 'N/A'}`"
            )
            st.write(item.get("content", ""))


def render_question_box() -> None:
    st.markdown(
        """
        <section class="advisor-composer">
        <section class="advisor-input-panel">
            <div class="advisor-input-title">Ask your advisor</div>
            <div class="advisor-input-help">Share your target country, degree level, scores, budget, preferred major, or school list.</div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    with st.form("advisor_question_form", clear_on_submit=True):
        question = st.text_area(
            "Your question",
            label_visibility="collapsed",
            placeholder=(
                "Example: I want a master's in computer science, IELTS 6.5, budget around $35k/year, "
                "and I care about scholarships and post-study work options. What schools or countries should I consider?"
            ),
            height=140,
        )
        submitted = st.form_submit_button("Send question", use_container_width=True)
    if submitted and question.strip():
        st.session_state.pending_prompt = question.strip()
        st.markdown("</section>", unsafe_allow_html=True)
        st.rerun()
    st.markdown("</section>", unsafe_allow_html=True)


def main() -> None:
    debug_enabled = os.getenv("ADVISOR_DEBUG", "").lower() in {"1", "true", "yes", "on"}
    st.set_page_config(
        page_title="International Admissions Advisor",
        layout="wide",
        initial_sidebar_state="expanded" if debug_enabled else "collapsed",
    )
    init_state()
    options = sidebar_options()
    apply_page_style()
    render_header()
    render_prompt_buttons()

    st.markdown('<section class="advisor-chat-area">', unsafe_allow_html=True)
    for message in st.session_state.messages:
        avatar = str(ADVISOR_AVATAR) if message["role"] == "assistant" else None
        with st.chat_message(message["role"], avatar=avatar):
            st.markdown(message["content"])
            if options["show_context"] and message["role"] == "assistant" and message.get("retrieval"):
                render_debug_context(message["retrieval"])

    if st.session_state.pending_prompt:
        user_input = st.session_state.pending_prompt
        st.session_state.pending_prompt = None
        handle_user_turn(user_input, options)
    st.markdown("</section>", unsafe_allow_html=True)

    render_question_box()


if __name__ == "__main__":
    main()
