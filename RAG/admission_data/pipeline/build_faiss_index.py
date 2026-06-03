from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
RAG_DIR = ROOT / "data" / "clean" / "rag"
DEFAULT_INPUTS = [RAG_DIR / "rag_embeddings_openai_3_small.jsonl"]
DEFAULT_INDEX = RAG_DIR / "rag_openai_3_small.faiss"
DEFAULT_METADATA = RAG_DIR / "rag_openai_3_small_metadata.jsonl"
DEFAULT_MANIFEST = RAG_DIR / "rag_openai_3_small_faiss_manifest.json"


def load_embedding_rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local FAISS vector index from embedding JSONL.")
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="Embedding JSONL file. Can be passed multiple times.",
    )
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="Output FAISS index path")
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA), help="Output metadata JSONL path")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Output manifest JSON path")
    parser.add_argument("--batch-size", type=int, default=2048, help="Vectors to add per FAISS batch")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_paths = [Path(path) for path in args.input] or DEFAULT_INPUTS
    index_path = Path(args.index)
    metadata_path = Path(args.metadata)
    manifest_path = Path(args.manifest)

    import faiss

    index = None
    vector_count = 0
    dimensions = None
    batch = []
    model = None

    def flush() -> None:
        nonlocal batch, vector_count
        if not batch:
            return
        matrix = np.asarray(batch, dtype="float32")
        index.add(matrix)
        vector_count += len(batch)
        if vector_count % 10000 < len(batch):
            print(f"Indexed {vector_count:,} vectors")
        batch = []

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("w", encoding="utf-8") as metadata_handle:
        for input_path in input_paths:
            for row in load_embedding_rows(input_path):
                embedding = row.get("embedding") or []
                if not embedding:
                    continue
                if dimensions is None:
                    dimensions = len(embedding)
                    index = faiss.IndexFlatIP(dimensions)
                if len(embedding) != dimensions:
                    raise ValueError(f"Dimension mismatch for {row.get('doc_id')}: {len(embedding)} != {dimensions}")
                model = model or row.get("model")
                batch.append(embedding)
                metadata_handle.write(
                    json.dumps(
                        {
                            "doc_id": row.get("doc_id"),
                            "custom_id": row.get("custom_id"),
                            "model": row.get("model"),
                            "metadata": row.get("metadata", {}),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                if len(batch) >= args.batch_size:
                    flush()
        flush()

    if index is None or dimensions is None:
        raise SystemExit("No vectors found.")

    faiss.write_index(index, str(index_path))
    manifest = {
        "inputs": [
            str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path) for path in input_paths
        ],
        "index": str(index_path.relative_to(ROOT)) if index_path.is_relative_to(ROOT) else str(index_path),
        "metadata": str(metadata_path.relative_to(ROOT)) if metadata_path.is_relative_to(ROOT) else str(metadata_path),
        "model": model,
        "metric": "inner_product_on_normalized_vectors",
        "dimensions": dimensions,
        "vector_count": vector_count,
        "index_type": "faiss.IndexFlatIP",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote FAISS index: {index_path}")
    print(f"Wrote metadata: {metadata_path}")
    print(f"Wrote manifest: {manifest_path}")


if __name__ == "__main__":
    main()
