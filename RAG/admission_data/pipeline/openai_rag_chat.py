from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from openai import OpenAI

from advisor_common import SYSTEM_PROMPT, compact_contexts, load_local_env, sanitize_client_answer
from retrieve_context import (
    DOC_TYPE_CHOICES,
    DEFAULT_DOCS,
    DEFAULT_OPENAI_INDEX,
    DEFAULT_OPENAI_METADATA,
    OPENAI_EMBEDDING_MODEL,
    retrieve_context,
)


DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_MAX_OUTPUT_TOKENS = 700
DEFAULT_CONTEXT_CHARS = 4500


def call_openai_response(
    *,
    model: str,
    instructions: str,
    user_content: str,
    temperature: float,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> str:
    client = OpenAI()
    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=user_content,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    return response.output_text


def build_retrieval_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        query=args.query,
        index=args.index,
        metadata=args.metadata,
        docs=args.docs,
        model=args.embedding_model,
        device=args.device,
        limit=args.context_limit,
        search_k=args.search_k,
        doc_type=args.doc_type,
        school_id=args.school_id,
        country=args.country,
        program_level=args.program_level,
        exclude_stale=args.exclude_stale,
        pretty=False,
    )


def parse_args() -> argparse.Namespace:
    load_local_env()
    parser = argparse.ArgumentParser(description="Run local RAG retrieval and answer with OpenAI.")
    parser.add_argument("query", help="User question")
    parser.add_argument("--index", default=str(DEFAULT_OPENAI_INDEX))
    parser.add_argument("--metadata", default=str(DEFAULT_OPENAI_METADATA))
    parser.add_argument("--docs", default=str(DEFAULT_DOCS))
    parser.add_argument("--embedding-model", default=OPENAI_EMBEDDING_MODEL)
    parser.add_argument("--device", default="cpu", help="Only used for non-OpenAI local embedding models")
    parser.add_argument("--context-limit", type=int, default=int(os.getenv("RAG_CONTEXT_LIMIT", "4")))
    parser.add_argument("--context-chars", type=int, default=int(os.getenv("RAG_CONTEXT_CHARS", str(DEFAULT_CONTEXT_CHARS))))
    parser.add_argument("--search-k", type=int, default=int(os.getenv("RAG_SEARCH_K", "500")))
    parser.add_argument("--doc-type", choices=DOC_TYPE_CHOICES)
    parser.add_argument("--school-id")
    parser.add_argument("--country")
    parser.add_argument("--program-level", choices=["undergrad", "master", "phd", "certificate", "unknown"])
    parser.add_argument("--exclude-stale", action="store_true")
    parser.add_argument("--openai-model", default=os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL))
    parser.add_argument("--max-output-tokens", type=int, default=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", str(DEFAULT_MAX_OUTPUT_TOKENS))))
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--show-context", action="store_true", help="Print retrieved clean context JSON with the answer")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set. Add it to admission_data/.env or export it first.")

    retrieval = retrieve_context(build_retrieval_args(args))
    context_text = compact_contexts(retrieval["contexts"], max_chars=args.context_chars)
    if not context_text:
        context_text = "No verified private facts were found for this question. Provide general admissions guidance only."

    user_content = (
        f"Private facts for internal use only:\n{context_text}\n\n"
        f"User question: {args.query}\n\n"
        "Answer from these facts first if they directly answer the question. Use natural, parent-and-student-friendly wording. "
        "If recommending schools or countries, prioritize options represented in the available school/program list. "
        "Use program/admission/school facts as the base, and use rankings only as reputation support. "
        "Create a balanced shortlist with safer, good-fit, and slightly challenging options when possible. "
        "Do not put schools in the main list if the student clearly misses a hard requirement. "
        "Keep the answer brief by default, usually under 180 words unless the user asks for detail. "
        "If the facts are missing or weak, give general expert guidance. "
        "Do not reveal or refer to the private facts, notes, source URLs, or scrape details."
    )
    answer = call_openai_response(
        model=args.openai_model,
        instructions=SYSTEM_PROMPT,
        user_content=user_content,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
    )
    print(sanitize_client_answer(answer))
    if args.show_context:
        print("\n--- Retrieved Context ---")
        print(json.dumps(retrieval, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
