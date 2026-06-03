from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import numpy as np

from advisor_common import load_local_env


ROOT = Path(__file__).resolve().parents[1]
RAG_DIR = ROOT / "data" / "clean" / "rag"
DEFAULT_INDEX = RAG_DIR / "rag_openai_3_small.faiss"
DEFAULT_METADATA = RAG_DIR / "rag_openai_3_small_metadata.jsonl"
DEFAULT_OPENAI_INDEX = RAG_DIR / "rag_openai_3_small.faiss"
DEFAULT_OPENAI_METADATA = RAG_DIR / "rag_openai_3_small_metadata.jsonl"
DEFAULT_DOCS = RAG_DIR / "rag_documents_with_supplemental.jsonl"
DEFAULT_MODEL = "text-embedding-3-small"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
DOC_TYPE_CHOICES = [
    "program",
    "admission_page",
    "school_page",
    "scholarship",
    "deadline",
    "tuition",
    "requirement",
    "university_ranking",
    "country_advice",
    "program_advice",
]


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
    if args.exclude_stale and metadata.get("has_stale_date"):
        return False
    return True


def strip_internal_labels(text: str) -> str:
    text = normalize_text(text)
    text = re.sub(r"\bSource URL:\s*\S+", "", text)
    text = re.sub(r"^Document type:\s*[a-z_]+\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bDocument type:\s*[^:]+(?=\s+School:|\s+Content:|$)", "", text)
    text = normalize_text(text)
    return text


def context_title(metadata: dict) -> str:
    pieces = []
    if metadata.get("university_name"):
        pieces.append(metadata["university_name"])
    if metadata.get("ranking_name"):
        pieces.append(metadata["ranking_name"])
    if metadata.get("school_name"):
        pieces.append(metadata["school_name"])
    if metadata.get("program_name"):
        pieces.append(metadata["program_name"])
    if metadata.get("country") and metadata.get("doc_type") in {"country_advice", "program_advice"}:
        pieces.append(metadata["country"])
    if metadata.get("doc_type"):
        pieces.append(str(metadata["doc_type"]).replace("_", " ").title())
    return " - ".join(pieces) or "Retrieved Context"


def quality_boost(query: str, text: str, metadata: dict) -> float:
    query_l = query.lower()
    text_l = text.lower()
    boost = 0.0
    if any(term in query_l for term in ("ielts", "toefl", "duolingo", "pte", "gpa", "requirement", "requirements")):
        if re.search(r"\b(ielts|toefl|duolingo|pte|gpa)\b", text_l):
            boost += 0.12
        if re.search(r"\b\d+(?:\.\d+)?\b", text_l):
            boost += 0.04
    if any(term in query_l for term in ("scholarship", "scholarships", "financial aid", "aid")):
        if re.search(r"\b(scholarship|scholarships|grant|award|financial aid)\b", text_l):
            boost += 0.08
        if re.search(r"(\$|usd|aud|cad|gbp|eur|amount|tuition)", text_l):
            boost += 0.03
    if any(term in query_l for term in ("deadline", "date", "intake", "apply")):
        if re.search(r"\b(deadline|intake|apply|application)\b", text_l):
            boost += 0.08
        if metadata.get("has_stale_date"):
            boost -= 0.03
    if len(text_l) < 80:
        boost -= 0.08
    return boost


def token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9.]+", text.lower()))


def too_similar(text: str, existing_texts: list[str], threshold: float = 0.82) -> bool:
    tokens = token_set(text)
    if not tokens:
        return False
    for existing in existing_texts:
        other = token_set(existing)
        if not other:
            continue
        overlap = len(tokens & other) / max(1, len(tokens | other))
        if overlap >= threshold:
            return True
    return False


def normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return matrix / norms


def embed_query(args: argparse.Namespace) -> np.ndarray:
    if str(args.model).startswith("text-embedding"):
        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is not set. Add it to admission_data/.env or export it first.")
        from openai import OpenAI

        request = {"model": args.model, "input": args.query}
        dimensions = getattr(args, "dimensions", None)
        if dimensions:
            request["dimensions"] = dimensions
        response = OpenAI().embeddings.create(**request)
        matrix = np.asarray([response.data[0].embedding], dtype="float32")
        return normalize_matrix(matrix)

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(args.model, trust_remote_code=True, device=args.device)
    query_vector = model.encode([args.query], normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(query_vector, dtype="float32")


def parse_args() -> argparse.Namespace:
    load_local_env()
    parser = argparse.ArgumentParser(description="Retrieve clean chatbot context from the local FAISS RAG index.")
    parser.add_argument("query", help="Natural language user question")
    parser.add_argument("--index", default=str(DEFAULT_INDEX))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--docs", default=str(DEFAULT_DOCS))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--dimensions", type=int, help="Optional OpenAI embedding dimensions if the index was built with reduced dimensions")
    parser.add_argument("--device", default="cpu", help="Use cpu for stable one-off query embedding")
    parser.add_argument("--limit", type=int, default=8, help="Clean context items to return")
    parser.add_argument("--search-k", type=int, default=200, help="Initial vector candidates")
    parser.add_argument("--doc-type", choices=DOC_TYPE_CHOICES)
    parser.add_argument("--school-id")
    parser.add_argument("--country")
    parser.add_argument("--program-level", choices=["undergrad", "master", "phd", "certificate", "unknown"])
    parser.add_argument("--exclude-stale", action="store_true", help="Exclude chunks with stale dates")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser.parse_args()


def retrieve_context(args: argparse.Namespace) -> dict:
    query_matrix = embed_query(args)

    import faiss

    index = faiss.read_index(str(Path(args.index)))
    metadata_rows = load_metadata(Path(args.metadata))
    if index.ntotal != len(metadata_rows):
        raise SystemExit(f"Index/metadata count mismatch: {index.ntotal} != {len(metadata_rows)}")
    scores, indices = index.search(query_matrix, args.search_k)

    candidates = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        row = metadata_rows[int(idx)]
        if not matches_filters(row, args):
            continue
        candidates.append((float(score), row))

    doc_texts = load_doc_texts(Path(args.docs), {row.get("doc_id") for _, row in candidates})
    scored_candidates = []
    for score, row in candidates:
        doc_id = row.get("doc_id")
        raw_text = doc_texts.get(doc_id, "")
        boosted_score = score + quality_boost(args.query, raw_text, row.get("metadata", {}))
        scored_candidates.append((boosted_score, score, row))
    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    contexts = []
    accepted_texts: list[str] = []
    for boosted_score, raw_score, row in scored_candidates:
        metadata = row.get("metadata", {})
        doc_id = row.get("doc_id")
        content = strip_internal_labels(doc_texts.get(doc_id, ""))
        if not content:
            continue
        if too_similar(content, accepted_texts):
            continue
        accepted_texts.append(content)
        contexts.append(
            {
                "title": context_title(metadata),
                "content": content,
                "score": round(boosted_score, 4),
                "vector_score": round(raw_score, 4),
                "school_id": metadata.get("school_id"),
                "school_name": metadata.get("school_name"),
                "country": metadata.get("country"),
                "program_name": metadata.get("program_name"),
                "program_level": metadata.get("program_level"),
                "doc_type": metadata.get("doc_type"),
                "fact_key": metadata.get("fact_key"),
                "deadline_status": metadata.get("deadline_status"),
                "has_stale_date": metadata.get("has_stale_date"),
            }
        )
        if len(contexts) >= args.limit:
            break

    return {
        "query": args.query,
        "model": args.model,
        "contexts": contexts,
        "client_hidden_fields": [
            "source_url",
            "source_file",
            "doc_id",
            "parent_id",
            "replace_scope",
            "dedupe_key",
            "scrape metadata",
        ],
    }


def main() -> None:
    args = parse_args()
    response = retrieve_context(args)
    print(json.dumps(response, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
