from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAG_DOCUMENTS_JSONL = ROOT / "data" / "clean" / "rag" / "rag_documents.jsonl"

TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "does",
    "for",
    "from",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "school",
    "show",
    "tell",
    "the",
    "this",
    "to",
    "university",
    "what",
    "with",
}


def tokenize(text: str | None) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "") if token.lower() not in STOPWORDS]


def load_documents(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def metadata_text(doc: dict) -> str:
    metadata = doc.get("metadata", {})
    values = [
        doc.get("doc_type"),
        metadata.get("school_id"),
        metadata.get("school_name"),
        metadata.get("country"),
        metadata.get("program_name"),
        metadata.get("program_level"),
        metadata.get("fact_key"),
        metadata.get("deadline_status"),
    ]
    return " ".join(str(value) for value in values if value)


def matches_filters(doc: dict, args: argparse.Namespace) -> bool:
    metadata = doc.get("metadata", {})
    if args.doc_type and doc.get("doc_type") != args.doc_type:
        return False
    if args.school_id and metadata.get("school_id") != args.school_id:
        return False
    if args.country and (metadata.get("country") or "").lower() != args.country.lower():
        return False
    if args.program_level and metadata.get("program_level") != args.program_level:
        return False
    if args.fact_key and metadata.get("fact_key") != args.fact_key:
        return False
    if args.only_stale and not metadata.get("has_stale_date"):
        return False
    return True


def score_document(doc: dict, query_terms: list[str], query_phrase: str) -> float:
    text = doc.get("text", "")
    metadata = metadata_text(doc)
    text_terms = Counter(tokenize(text))
    metadata_terms = Counter(tokenize(metadata))

    score = 0.0
    for term in query_terms:
        score += math.log1p(text_terms.get(term, 0)) * 2.0
        score += math.log1p(metadata_terms.get(term, 0)) * 4.0

    lower_text = text.lower()
    lower_metadata = metadata.lower()
    lower_query = query_phrase.lower().strip()
    if lower_query and lower_query in lower_text:
        score += 10.0
    if lower_query and lower_query in lower_metadata:
        score += 14.0

    if doc.get("doc_type") == "program" and any(term in query_terms for term in {"program", "course", "major"}):
        score += 1.5
    if doc.get("metadata", {}).get("has_stale_date") and any(term in query_terms for term in {"deadline", "date"}):
        score += 0.5

    return score


def preview(text: str, max_chars: int = 700) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def print_result(rank: int, doc: dict, score: float) -> None:
    metadata = doc.get("metadata", {})
    print(f"\n#{rank} score={score:.2f}")
    print(f"doc_id: {doc.get('doc_id')}")
    print(f"doc_type: {doc.get('doc_type')}")
    print(f"school: {metadata.get('school_name')} ({metadata.get('school_id')})")
    if metadata.get("program_name"):
        print(f"program: {metadata.get('program_name')} [{metadata.get('program_level')}]")
    if metadata.get("fact_key"):
        print(f"fact_key: {metadata.get('fact_key')}")
    print(f"deadline_status: {metadata.get('deadline_status')} stale={metadata.get('has_stale_date')}")
    print(f"source_url: {metadata.get('source_url')}")
    print(f"text: {preview(doc.get('text', ''))}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search local RAG JSONL documents without a vector database.")
    parser.add_argument("query", help="Search query, for example: 'scholarships University at Albany'")
    parser.add_argument("--path", default=str(RAG_DOCUMENTS_JSONL), help="Path to rag_documents.jsonl")
    parser.add_argument("--limit", type=int, default=5, help="Number of results to print")
    parser.add_argument(
        "--doc-type",
        choices=[
            "program",
            "admission_page",
            "school_page",
            "scholarship",
            "deadline",
            "tuition",
            "requirement",
        ],
        help="Filter by doc_type",
    )
    parser.add_argument("--school-id", help="Filter by school_id, for example US00001")
    parser.add_argument("--country", help="Filter by country, for example usa")
    parser.add_argument("--program-level", choices=["undergrad", "master", "phd", "certificate", "unknown"])
    parser.add_argument("--fact-key", help="Filter by fact_key, for example scholarship or admission_summary")
    parser.add_argument("--only-stale", action="store_true", help="Only show docs with stale dates")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.path)
    query_terms = tokenize(args.query)
    if not query_terms:
        raise SystemExit("Query has no searchable terms.")

    scored = []
    scanned = 0
    for doc in load_documents(path):
        if not matches_filters(doc, args):
            continue
        scanned += 1
        score = score_document(doc, query_terms, args.query)
        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda item: item[0], reverse=True)
    print(f"Scanned {scanned:,} filtered docs. Found {len(scored):,} matching docs.")
    for rank, (score, doc) in enumerate(scored[: args.limit], start=1):
        print_result(rank, doc, score)


if __name__ == "__main__":
    main()
