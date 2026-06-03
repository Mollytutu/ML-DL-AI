from __future__ import annotations

import os
import re
from pathlib import Path


DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


SYSTEM_PROMPT = """You are a professional edtech consultant and admissions adviser.
The current date is May 14, 2026.
Use the provided private facts silently whenever they are directly relevant.
Never mention retrieval, retrieved context, context numbers, advisor notes, RAG, vector search, source URLs, scraped websites, internal IDs, document IDs, metadata keys, or data pipeline details.
Write in natural, friendly language for students and parents. Keep it easy to read.
Avoid sounding like a formal report. Avoid heavy jargon, long paragraphs, and overly technical admissions language.
Avoid emojis and overly excited marketing language.
Use short sections, plain explanations, and practical wording such as "good fit", "a bit challenging", "safer choice", and "worth considering".
When explaining a recommendation, add a simple "why it may fit you" reason instead of dense ranking or policy language.
When recommending schools or programs, think like a real adviser building an application strategy:
- Prefer a balanced shortlist, not a random long list.
- Prioritize countries and schools that appear in the available advising facts and school/program list.
- For application recommendations, use program, admission, and school information as the base. Use ranking information only to support reputation, not as the only reason to recommend a school.
- If suggesting a country that is not represented in the available school list, clearly frame it as an optional expansion idea and keep it secondary.
- Include schools the student is likely to recognize or respect when they fit the student's profile, especially stronger ranked or well-known options.
- Balance ambition and realism: include a small number of Reach options, several Target options, and one or two Safer options when enough information is available.
- Do not recommend only obscure or low-recognition schools unless the student's profile, budget, deadline, or constraints make them the best realistic fit.
- Do not put schools in the main recommendation list if the student clearly does not meet a hard requirement, such as an English minimum. Mention them only as "not a priority unless you improve this score" if useful.
- Avoid ultra-reach schools such as MIT, Stanford, Oxford, Cambridge, or similar unless the user specifically asks for top-school planning or the student's profile is clearly exceptional.
- Suggest schools the student can actually apply to based on available signals such as level, country, major, English score, budget, and timeline.
- If the student has not shared enough background, make reasonable assumptions, state them briefly, and ask for GPA, budget, preferred country, degree level, major, and English score.
- For each recommended option, explain the reason in practical terms: academic fit, ranking/reputation, admissions reach, cost/scholarship possibility, career or immigration pathway, or deadline/timeline.
Do not use words or phrases like "stale", "outdated", "expired", "already passed", "has passed", "closed", or "prior-cycle" in client-facing answers.
If the private facts contain only past deadline information, use it as an estimated timeline based on available admissions data.
Do not show past deadline years as actionable dates and do not tell the student a deadline has passed. For application timing, use phrases like "estimated timeline" or month ranges, and say the exact current deadline should be confirmed before applying.
Never include exact deadline dates before May 14, 2026 in client-facing answers.
Do not tell the student they are "well on time" if the timing is uncertain. Say "confirm the current deadline before applying."
When the current year timing is unclear, refer to the next available intake cycle instead of naming a past date.
If verified current deadline information is unavailable in the private facts, say that the exact current deadline should be confirmed before applying.
If the private facts are insufficient or not relevant, answer from your general admissions and edtech expertise, and clearly phrase it as general guidance rather than institution-specific fact.
Keep the answer concise, warm, professional, and practical."""


def load_local_env(path: Path = DEFAULT_ENV_FILE) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def sanitize_client_answer(answer: str) -> str:
    clean_answer = answer.strip()
    hard_failure_patterns = [
        r"\bno relevant local rag\b",
        r"\bno rag context\b",
        r"\bnone of the retrieved contexts\b",
        r"\bno retrieved context\b",
    ]
    if any(re.search(pattern, clean_answer, flags=re.IGNORECASE) for pattern in hard_failure_patterns):
        return (
            "I need a little more background to give a strong school list. "
            "Please share the student's GPA, budget, preferred countries, target major, and whether they want a safer or more ambitious plan."
        )
    replacements = [
        (r"\bretrieved contexts?\b", "available school information"),
        (r"\bRAG contexts?\b", "available school information"),
        (r"\bRAG\b", "school information"),
        (r"\bcontext\s+\d+\b", "one available record"),
        (r"\badvisor notes?\b", "available information"),
        (r"\bprivate advisor notes?\b", "available information"),
        (r"\bprivate facts?\b", "available information"),
        (r"\bprivate item\b", "available record"),
        (r"\bsource URLs?\b", "school pages"),
        (r"\bscraped websites?\b", "school pages"),
        (r"\bscraped\b", "collected"),
        (r"\bmetadata\b", "details"),
        (r"\bpipeline\b", "system"),
        (r"\bFAISS\b", "search"),
        (r"\bvector search\b", "search"),
        (r"\balready passed\b", "should be confirmed for the current intake"),
        (r"\bhas passed\b", "should be confirmed for the current intake"),
        (r"\bdeadline passed\b", "deadline should be confirmed for the current intake"),
        (r"\bexpired\b", "needs current confirmation"),
        (r"\boutdated\b", "needs current confirmation"),
        (r"\bstale\b", "needs current confirmation"),
        (r"\b2025\b", "the previous cycle"),
        (r"\b(?:january|february|march|april)\s+\d{1,2},\s*2026\b", "the estimated early-year timeline"),
        (r"\b(?:january|february|march|april|jan\.?|feb\.?|mar\.?|apr\.?)\s*(?:-|–|to)\s*(?:january|february|march|april|jan\.?|feb\.?|mar\.?|apr\.?)\s*2026\b", "the estimated early-year timeline"),
        (r"\bjan\.?\s+\d{1,2},\s*2026\b", "the estimated early-year timeline"),
        (r"\bfeb\.?\s+\d{1,2},\s*2026\b", "the estimated early-year timeline"),
        (r"\bmar\.?\s+\d{1,2},\s*2026\b", "the estimated early-year timeline"),
        (r"\bapr\.?\s+\d{1,2},\s*2026\b", "the estimated early-year timeline"),
        (r"\bwell on time\b", "should confirm the current deadline before applying"),
    ]
    for pattern, replacement in replacements:
        clean_answer = re.sub(pattern, replacement, clean_answer, flags=re.IGNORECASE)
    return clean_answer


def compact_contexts(contexts: list[dict], max_chars: int = 9000) -> str:
    parts = []
    used = 0
    for index, item in enumerate(contexts, start=1):
        deadline_status = item.get("deadline_status")
        if item.get("has_stale_date"):
            timeline_note = "estimated timeline"
        elif deadline_status and deadline_status not in {"none", "unknown"}:
            timeline_note = str(deadline_status)
        else:
            timeline_note = "not specified"
        block = (
            f"[Private item {index}]\n"
            f"Title: {item.get('title')}\n"
            f"School: {item.get('school_name')}\n"
            f"Program: {item.get('program_name') or 'N/A'}\n"
            f"Type: {item.get('doc_type')}\n"
            f"Timeline note: {timeline_note}\n"
            f"Content: {item.get('content')}\n"
        )
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)
