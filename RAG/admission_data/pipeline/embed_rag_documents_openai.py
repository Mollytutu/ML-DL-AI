from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np
from openai import OpenAI, RateLimitError

from advisor_common import load_local_env


ROOT = Path(__file__).resolve().parents[1]
RAG_DIR = ROOT / "data" / "clean" / "rag"
DEFAULT_INPUT = RAG_DIR / "rag_documents_openai_unique.jsonl"
DEFAULT_OUTPUT = RAG_DIR / "rag_embeddings_openai_3_small.jsonl"
DEFAULT_MODEL = "text-embedding-3-small"


def load_jsonl(path: Path, limit: int | None = None):
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            yield json.loads(line)
            count += 1
            if limit and count >= limit:
                break


def load_existing_doc_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            doc_id = record.get("doc_id") or record.get("custom_id")
            if doc_id:
                seen.add(doc_id)
    return seen


def normalize_vector(vector: list[float]) -> list[float]:
    array = np.asarray(vector, dtype="float32")
    norm = float(np.linalg.norm(array))
    if norm:
        array = array / norm
    return array.tolist()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate OpenAI embeddings from RAG JSONL documents.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input RAG JSONL path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output embeddings JSONL path")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI embedding model")
    parser.add_argument("--dimensions", type=int, help="Optional embedding dimensions for supported OpenAI embedding models")
    parser.add_argument("--batch-size", type=int, default=100, help="Documents per embeddings API request")
    parser.add_argument("--limit", type=int, help="Only embed the first N documents for testing")
    parser.add_argument("--append", action="store_true", help="Append to output instead of replacing it")
    parser.add_argument("--resume", action="store_true", help="Append and skip doc_ids already present in output")
    parser.add_argument("--progress-every", type=int, default=1000, help="Print progress after this many new embeddings")
    parser.add_argument("--max-retries", type=int, default=8, help="Retries for temporary OpenAI rate limits")
    return parser.parse_args()


def main() -> None:
    load_local_env()
    args = parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set. Add it to admission_data/.env or export it first.")

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = OpenAI()
    existing_doc_ids = load_existing_doc_ids(output_path) if args.resume else set()
    if existing_doc_ids:
        print(f"Resume mode: found {len(existing_doc_ids):,} existing embeddings in {output_path}")

    mode = "a" if args.append or args.resume else "w"
    total = 0
    skipped = 0
    last_reported = 0
    docs: list[dict] = []
    texts: list[str] = []

    def flush(handle) -> None:
        nonlocal total, docs, texts, last_reported
        if not docs:
            return
        request = {"model": args.model, "input": texts}
        if args.dimensions:
            request["dimensions"] = args.dimensions
        for attempt in range(args.max_retries + 1):
            try:
                response = client.embeddings.create(**request)
                break
            except RateLimitError:
                if attempt >= args.max_retries:
                    raise
                sleep_seconds = min(2 ** attempt, 30)
                print(f"Rate limited. Retrying in {sleep_seconds}s...")
                time.sleep(sleep_seconds)
        vectors = [item.embedding for item in response.data]
        for doc, vector in zip(docs, vectors):
            record = {
                "doc_id": doc.get("doc_id"),
                "custom_id": doc.get("doc_id"),
                "model": args.model,
                "dimensions": args.dimensions,
                "embedding": normalize_vector(vector),
                "metadata": {
                    **doc.get("metadata", {}),
                    "doc_type": doc.get("doc_type"),
                    "parent_id": doc.get("parent_id"),
                },
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            total += 1
        if total - last_reported >= args.progress_every:
            print(f"Embedded {total:,} new documents")
            last_reported = total
        docs = []
        texts = []

    with output_path.open(mode, encoding="utf-8") as handle:
        for doc in load_jsonl(input_path, args.limit):
            doc_id = doc.get("doc_id")
            if doc_id in existing_doc_ids:
                skipped += 1
                continue
            text = (doc.get("text") or "").strip()
            if not text:
                continue
            docs.append(doc)
            texts.append(text.replace("\n", " "))
            if len(docs) >= args.batch_size:
                flush(handle)
        flush(handle)

    print(f"Skipped {skipped:,} existing embeddings")
    print(f"Wrote {total:,} new embeddings to {output_path}")


if __name__ == "__main__":
    main()
