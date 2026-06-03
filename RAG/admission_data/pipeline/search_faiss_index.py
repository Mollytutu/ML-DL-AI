from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from advisor_common import load_local_env
from retrieve_context import (
    DEFAULT_DOCS,
    DEFAULT_OPENAI_INDEX,
    DEFAULT_OPENAI_METADATA,
    DOC_TYPE_CHOICES,
    OPENAI_EMBEDDING_MODEL,
    embed_query,
)


ROOT = Path(__file__).resolve().parents[1]
RAG_DIR = ROOT / "data" / "clean" / "rag"
DEFAULT_INDEX = DEFAULT_OPENAI_INDEX
DEFAULT_METADATA = DEFAULT_OPENAI_METADATA
DEFAULT_MODEL = OPENAI_EMBEDDING_MODEL


def normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def load_metadata(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_doc_texts(path: Path, wanted_doc_ids: set[str]) -> dict[str, str]:
    texts = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            doc_id = row.get("doc_id")
            if doc_id in wanted_doc_ids:
                texts.setdefault(doc_id, row.get("text", ""))
                if len(texts) >= len(wanted_doc_ids):
                    break
    return texts


def matches_filters(row: dict, args: argparse.Namespace) -> bool:
    metadata = row.get("metadata", {})
    if args.doc_type and metadata.get("doc_type") != args.doc_type:
        return False
    if args.school_id and metadata.get("school_id") != args.school_id:
        return False
    if args.country and (metadata.get("country") or "").lower() != args.country.lower():
        return False
    if args.program_level and metadata.get("program_level") != args.program_level:
        return False
    if args.only_stale and not metadata.get("has_stale_date"):
        return False
    return True


def preview(text: str, max_chars: int = 900) -> str:
    text = normalize_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search the local FAISS RAG index.")
    parser.add_argument("query", help="Natural language query")
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="FAISS index path")
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA), help="Metadata JSONL path")
    parser.add_argument("--docs", default=str(DEFAULT_DOCS), help="RAG docs JSONL path for text preview")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Embedding model for query embedding")
    parser.add_argument("--dimensions", type=int, help="Optional OpenAI embedding dimensions if the index was built with reduced dimensions")
    parser.add_argument("--device", default="cpu", help="Torch device for local models: mps, cpu, or cuda")
    parser.add_argument("--limit", type=int, default=5, help="Results to print after filtering")
    parser.add_argument("--search-k", type=int, default=80, help="Initial FAISS candidates before metadata filtering")
    parser.add_argument("--doc-type", choices=DOC_TYPE_CHOICES)
    parser.add_argument("--school-id", help="Filter by school_id")
    parser.add_argument("--country", help="Filter by country")
    parser.add_argument("--program-level", choices=["undergrad", "master", "phd", "certificate", "unknown"])
    parser.add_argument("--only-stale", action="store_true", help="Only show stale-date docs")
    return parser.parse_args()


def main() -> None:
    load_local_env()
    args = parse_args()
    print(f"Embedding query with: {args.model}")
    query_matrix = embed_query(args)

    import faiss

    index = faiss.read_index(str(Path(args.index)))
    metadata_rows = load_metadata(Path(args.metadata))
    if index.ntotal != len(metadata_rows):
        raise SystemExit(f"Index/metadata count mismatch: {index.ntotal} != {len(metadata_rows)}")

    scores, indices = index.search(query_matrix, args.search_k)

    selected = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        row = metadata_rows[int(idx)]
        if not matches_filters(row, args):
            continue
        selected.append((float(score), row))
        if len(selected) >= args.limit:
            break

    doc_texts = load_doc_texts(Path(args.docs), {row.get("doc_id") for _, row in selected})

    printed = 0
    for score, row in selected:
        metadata = row.get("metadata", {})
        doc_id = row.get("doc_id")
        printed += 1
        print(f"\n#{printed} score={float(score):.4f}")
        print(f"doc_id: {doc_id}")
        print(f"doc_type: {metadata.get('doc_type')}")
        print(f"school: {metadata.get('school_name')} ({metadata.get('school_id')})")
        if metadata.get("program_name"):
            print(f"program: {metadata.get('program_name')} [{metadata.get('program_level')}]")
        if metadata.get("fact_key"):
            print(f"fact_key: {metadata.get('fact_key')}")
        print(f"deadline_status: {metadata.get('deadline_status')} stale={metadata.get('has_stale_date')}")
        print(f"source_url: {metadata.get('source_url')}")
        print(f"text: {preview(doc_texts.get(doc_id, ''))}")
    if printed == 0:
        print("No results after filters. Try raising --search-k or relaxing filters.")


if __name__ == "__main__":
    main()
