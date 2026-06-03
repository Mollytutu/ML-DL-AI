from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROGRAMS_CSV = ROOT / "data" / "clean" / "programs" / "programs.csv"
ADMISSIONS_CSV = ROOT / "data" / "clean" / "admission_pages" / "admission_pages.csv"
SCHOOL_PAGES_CSV = ROOT / "data" / "clean" / "school_pages" / "school_pages.csv"
RAG_DIR = ROOT / "data" / "clean" / "rag"
RAG_DOCUMENTS_JSONL = RAG_DIR / "rag_documents.jsonl"
RAG_MANIFEST_JSON = RAG_DIR / "rag_manifest.json"

MAX_CHUNK_WORDS = 420
CHUNK_OVERLAP_WORDS = 60

SCHOOL_PAGE_SKIP_KEYS = {
    "homepage_url",
    "school_country",
    "school_fact_status",
    "school_name",
    "school_page_type",
}

FACT_KEY_DOC_TYPE_MAP = {
    "scholarship": "scholarship",
    "deadline": "deadline",
    "tuition": "tuition",
    "exam_requirement": "requirement",
    "eligibility": "requirement",
    "intake": "deadline",
}

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

MONTH_NAME_RE = r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
DATE_PATTERNS = [
    re.compile(rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{MONTH_NAME_RE})[,]?\s+(?P<year>20\d{{2}})\b", re.I),
    re.compile(rf"\b(?P<month>{MONTH_NAME_RE})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(?P<year>20\d{{2}})\b", re.I),
]


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def read_csv(path: Path):
    csv.field_size_limit(sys.maxsize)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def parse_dates(text: str) -> list[date]:
    dates: list[date] = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text or ""):
            month = MONTHS.get(match.group("month").lower().rstrip("."))
            if not month:
                continue
            try:
                dates.append(date(int(match.group("year")), month, int(match.group("day"))))
            except ValueError:
                continue
    return sorted(set(dates))


def deadline_status(text: str, today: date) -> str:
    dates = parse_dates(text)
    if not dates:
        if re.search(r"\b(deadline|important date|intake|apply by|application)\b", text or "", re.I):
            return "unknown"
        return "none"
    has_past = any(item < today for item in dates)
    has_future = any(item >= today for item in dates)
    if has_past and has_future:
        return "mixed"
    if has_past:
        return "past"
    return "future"


def chunk_text(text: str, max_words: int = MAX_CHUNK_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    words = normalize_text(text).split()
    if len(words) <= max_words:
        return [" ".join(words)] if words else []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + max_words)
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = max(0, end - overlap)
    return chunks


def make_document(
    *,
    doc_type: str,
    source_file: str,
    text: str,
    metadata: dict,
    today: date,
    base_id: str,
) -> list[dict]:
    chunks = chunk_text(text)
    docs = []
    status = deadline_status(text, today)
    extracted_dates = [item.isoformat() for item in parse_dates(text)]
    for index, chunk in enumerate(chunks, start=1):
        doc_id = base_id if len(chunks) == 1 else f"{base_id}:chunk-{index:03d}"
        docs.append(
            {
                "doc_id": doc_id,
                "parent_id": base_id,
                "doc_type": doc_type,
                "text": chunk,
                "metadata": {
                    **metadata,
                    "source_file": source_file,
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                    "deadline_status": status,
                    "has_stale_date": status in {"past", "mixed"},
                    "extracted_dates": extracted_dates,
                    "build_date": today.isoformat(),
                    "data_status": "active",
                },
            }
        )
    return docs


def doc_type_for_fact(default_doc_type: str, fact_key: str | None) -> str:
    return FACT_KEY_DOC_TYPE_MAP.get(normalize_text(fact_key), default_doc_type)


def program_text(row: dict) -> str:
    parts = [
        ("School", row.get("school_name")),
        ("Country", row.get("country")),
        ("Program", row.get("program_name")),
        ("Program level", row.get("program_level")),
        ("Raw degree level", row.get("degree_level_raw")),
        ("Duration", row.get("duration")),
        ("Delivery mode", row.get("delivery_mode")),
        ("Language", row.get("language")),
        ("Study mode", row.get("study_mode")),
        ("Important date", row.get("important_date")),
        ("Tuition", row.get("tuition_local")),
        ("Currency", row.get("currency")),
        ("Entry requirement", row.get("entry_requirement")),
        ("Exam scores", row.get("exam_scores")),
        ("Program URL", row.get("program_url")),
    ]
    return "\n".join(f"{label}: {normalize_text(value)}" for label, value in parts if normalize_text(value))


def build_program_docs(today: date) -> list[dict]:
    docs: list[dict] = []
    for row in read_csv(PROGRAMS_CSV):
        text = program_text(row)
        if not text:
            continue
        program_key = row.get("program_url") or f"{row.get('school_id')}:{row.get('program_name')}"
        base_id = f"program:{row.get('school_id', 'unknown')}:{short_hash(program_key)}"
        docs.extend(
            make_document(
                doc_type="program",
                source_file=str(PROGRAMS_CSV.relative_to(ROOT)),
                text=text,
                today=today,
                base_id=base_id,
                metadata={
                    "school_id": row.get("school_id"),
                    "school_name": row.get("school_name"),
                    "country": row.get("country"),
                    "program_name": row.get("program_name"),
                    "program_level": row.get("program_level"),
                    "source_url": row.get("program_url") or row.get("source_programs_url"),
                    "school_homepage_url": row.get("school_homepage_url"),
                    "replace_scope": f"program:{row.get('school_id')}:{short_hash(program_key)}",
                },
            )
        )
    return docs


def fact_text(label: str, row: dict, school_name_field: str, url_field: str) -> str:
    school = normalize_text(row.get(school_name_field))
    country = normalize_text(row.get("country"))
    fact_key = normalize_text(row.get("fact_key")).replace("_", " ")
    fact_value = normalize_text(row.get("fact_value"))
    source_url = normalize_text(row.get(url_field) or row.get("source_url"))
    lines = [
        f"Document type: {label}",
        f"School: {school}" if school else "",
        f"Country: {country}" if country else "",
        f"Fact type: {fact_key}" if fact_key else "",
        f"Content: {fact_value}" if fact_value else "",
        f"Source URL: {source_url}" if source_url else "",
    ]
    return "\n".join(line for line in lines if line)


def build_admission_docs(today: date) -> list[dict]:
    docs: list[dict] = []
    for row in read_csv(ADMISSIONS_CSV):
        fact_value = normalize_text(row.get("fact_value"))
        if not fact_value:
            continue
        doc_type = doc_type_for_fact("admission_page", row.get("fact_key"))
        school_id = row.get("school_id") or "unknown"
        source_url = row.get("source_url") or row.get("admission_url") or ""
        base_key = f"{school_id}:{source_url}:{row.get('fact_key')}:{fact_value}"
        base_id = f"{doc_type}:{school_id}:{short_hash(base_key)}"
        docs.extend(
            make_document(
                doc_type=doc_type,
                source_file=str(ADMISSIONS_CSV.relative_to(ROOT)),
                text=fact_text("admission_page", row, "school_name_guess", "admission_url"),
                today=today,
                base_id=base_id,
                metadata={
                    "school_id": row.get("school_id"),
                    "school_name": row.get("school_name_guess"),
                    "country": row.get("country"),
                    "fact_key": row.get("fact_key"),
                    "source_url": source_url,
                    "admission_url": row.get("admission_url"),
                    "scraped_at": row.get("scraped_at"),
                    "source_layer": "admission_page",
                    "replace_scope": f"{doc_type}:{school_id}:{short_hash(source_url or school_id)}",
                },
            )
        )
    return docs


def build_school_page_docs(today: date) -> list[dict]:
    docs: list[dict] = []
    for row in read_csv(SCHOOL_PAGES_CSV):
        fact_key = normalize_text(row.get("fact_key"))
        fact_value = normalize_text(row.get("fact_value"))
        if not fact_value or fact_key in SCHOOL_PAGE_SKIP_KEYS:
            continue
        doc_type = doc_type_for_fact("school_page", fact_key)
        school_id = row.get("school_id") or "unknown"
        source_url = row.get("source_url") or ""
        base_key = f"{school_id}:{source_url}:{fact_key}:{fact_value}"
        base_id = f"{doc_type}:{school_id}:{short_hash(base_key)}"
        docs.extend(
            make_document(
                doc_type=doc_type,
                source_file=str(SCHOOL_PAGES_CSV.relative_to(ROOT)),
                text=fact_text("school_page", row, "school_name_guess", "source_url"),
                today=today,
                base_id=base_id,
                metadata={
                    "school_id": row.get("school_id"),
                    "school_name": row.get("school_name_guess"),
                    "country": row.get("country"),
                    "fact_key": fact_key,
                    "source_url": source_url,
                    "first_scraped_at": row.get("first_scraped_at"),
                    "last_scraped_at": row.get("last_scraped_at"),
                    "source_layer": "school_page",
                    "replace_scope": f"{doc_type}:{school_id}:{short_hash(source_url or school_id)}",
                },
            )
        )
    return docs


def write_outputs(docs: list[dict], today: date) -> None:
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    with RAG_DOCUMENTS_JSONL.open("w", encoding="utf-8") as handle:
        for doc in docs:
            handle.write(json.dumps(doc, ensure_ascii=False) + "\n")

    doc_type_counts = Counter(doc["doc_type"] for doc in docs)
    deadline_counts = Counter(doc["metadata"]["deadline_status"] for doc in docs)
    stale_counts = Counter(doc["doc_type"] for doc in docs if doc["metadata"]["has_stale_date"])
    manifest = {
        "build_date": today.isoformat(),
        "output": str(RAG_DOCUMENTS_JSONL.relative_to(ROOT)),
        "document_count": len(docs),
        "doc_type_counts": dict(sorted(doc_type_counts.items())),
        "deadline_status_counts": dict(sorted(deadline_counts.items())),
        "stale_date_doc_counts": dict(sorted(stale_counts.items())),
        "inputs": [
            str(PROGRAMS_CSV.relative_to(ROOT)),
            str(ADMISSIONS_CSV.relative_to(ROOT)),
            str(SCHOOL_PAGES_CSV.relative_to(ROOT)),
        ],
        "update_policy": [
            "Use doc_id for exact upsert/delete.",
            "Use metadata.replace_scope to refresh all chunks from one school/source layer.",
            "Use metadata.school_id + metadata.doc_type to refresh a full school layer.",
            "Do not append updated deadline docs without archiving or deleting older active docs for the same replace scope.",
        ],
    }
    RAG_MANIFEST_JSON.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build update-friendly JSONL documents for RAG ingestion.")
    parser.add_argument(
        "--today",
        default=date.today().isoformat(),
        help="Reference date for stale deadline detection, in YYYY-MM-DD format.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    today = datetime.strptime(args.today, "%Y-%m-%d").date()
    docs = []
    docs.extend(build_program_docs(today))
    docs.extend(build_admission_docs(today))
    docs.extend(build_school_page_docs(today))
    write_outputs(docs, today)
    print(f"Wrote {len(docs):,} RAG documents to {RAG_DOCUMENTS_JSONL}")
    print(f"Wrote manifest to {RAG_MANIFEST_JSON}")


if __name__ == "__main__":
    main()
