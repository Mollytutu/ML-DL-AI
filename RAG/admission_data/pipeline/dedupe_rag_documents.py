from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAG_DIR = ROOT / "data" / "clean" / "rag"
DEFAULT_INPUT = RAG_DIR / "rag_documents.jsonl"
DEFAULT_OUTPUT = RAG_DIR / "rag_documents_deduped.jsonl"
DEFAULT_MANIFEST = RAG_DIR / "rag_dedupe_manifest.json"


def normalize_text(text: str | None) -> str:
    text = re.sub(r"\s+", " ", text or "").strip().lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\bsource url:\s*", "", text)
    return text.strip()


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def dedupe_key(doc: dict) -> str:
    metadata = doc.get("metadata", {})
    key_parts = [
        doc.get("doc_type") or "",
        metadata.get("school_id") or "",
        metadata.get("program_name") or "",
        metadata.get("program_level") or "",
        metadata.get("fact_key") or "",
        normalize_text(doc.get("text")),
    ]
    return short_hash("\n".join(key_parts))


def load_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, docs: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for doc in docs:
            handle.write(json.dumps(doc, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remove duplicate local RAG documents before embedding.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input rag_documents.jsonl path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output deduped JSONL path")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Output manifest JSON path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    manifest_path = Path(args.manifest)

    seen = set()
    kept = []
    duplicate_counts = Counter()
    input_counts = Counter()
    kept_counts = Counter()
    duplicate_examples = []

    total = 0
    for doc in load_jsonl(input_path):
        total += 1
        doc_type = doc.get("doc_type") or "unknown"
        input_counts[doc_type] += 1
        key = dedupe_key(doc)
        if key in seen:
            duplicate_counts[doc_type] += 1
            if len(duplicate_examples) < 20:
                duplicate_examples.append(
                    {
                        "doc_id": doc.get("doc_id"),
                        "doc_type": doc_type,
                        "school_id": doc.get("metadata", {}).get("school_id"),
                        "school_name": doc.get("metadata", {}).get("school_name"),
                        "fact_key": doc.get("metadata", {}).get("fact_key"),
                    }
                )
            continue
        seen.add(key)
        doc["metadata"]["dedupe_key"] = key
        kept.append(doc)
        kept_counts[doc_type] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_path, kept)
    manifest = {
        "build_date": date.today().isoformat(),
        "input": str(input_path.relative_to(ROOT)) if input_path.is_relative_to(ROOT) else str(input_path),
        "output": str(output_path.relative_to(ROOT)) if output_path.is_relative_to(ROOT) else str(output_path),
        "input_document_count": total,
        "kept_document_count": len(kept),
        "removed_duplicate_count": total - len(kept),
        "input_doc_type_counts": dict(sorted(input_counts.items())),
        "kept_doc_type_counts": dict(sorted(kept_counts.items())),
        "removed_duplicate_doc_type_counts": dict(sorted(duplicate_counts.items())),
        "duplicate_examples": duplicate_examples,
        "dedupe_rule": "doc_type + school_id + program_name + program_level + fact_key + normalized text",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Read {total:,} docs")
    print(f"Kept {len(kept):,} docs")
    print(f"Removed {total - len(kept):,} duplicate docs")
    print(f"Wrote {output_path}")
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
