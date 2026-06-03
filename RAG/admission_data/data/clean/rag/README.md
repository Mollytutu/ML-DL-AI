# OpenAI RAG Output

This folder contains the local RAG assets for the admissions adviser chatbot.

Large generated files in this folder are intentionally ignored by git. For team or production use, keep code in GitHub and store the full vector data in Supabase/pgvector or another database-backed vector store.

The current runtime stack is:

- embeddings: `text-embedding-3-small`
- chat model: `gpt-4.1-mini`
- vector store: local FAISS
- app: `admission_data/app_streamlit.py`

## Runtime Files

These files are needed by the local FAISS chatbot, but they are not committed to GitHub because they are large generated artifacts:

- `rag_documents_with_supplemental.jsonl`: source text shown to the model after retrieval.
- `rag_openai_3_small.faiss`: FAISS vector index used for semantic search.
- `rag_openai_3_small_metadata.jsonl`: metadata aligned row-for-row with the FAISS index.
- `rag_openai_3_small_faiss_manifest.json`: index manifest with model, dimensions, and vector count.

Current index status:

- vectors: `193,457`
- dimensions: `1536`
- embedding model: `text-embedding-3-small`

## Build Files

These files are useful for rebuilding, but not all are needed at app runtime:

- `rag_documents_deduped.jsonl`: base RAG documents from programs, admission pages, and school pages.
- `rag_supplemental_documents.jsonl`: QS ranking and advice/pathway documents.
- `rag_documents_openai_unique.jsonl`: deduped OpenAI embedding input, one row per unique `doc_id`.
- `rag_embeddings_openai_3_small.jsonl`: raw OpenAI embedding output used to build FAISS.

`rag_embeddings_openai_3_small.jsonl` is very large and ignored by git. The app does not read it directly. Keep it only if you want to rebuild FAISS later without paying to embed again.

When moving to Supabase, import `doc_id`, chunk text, metadata, and the `text-embedding-3-small` vector into a `pgvector` table instead of uploading the `.faiss` file.

## Environment

Add secrets only to `admission_data/.env`. This file is ignored by git.

```bash
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MAX_OUTPUT_TOKENS=700
RAG_CONTEXT_LIMIT=4
RAG_CONTEXT_CHARS=4500
RAG_SEARCH_K=500
```

The token/context settings keep weekly OpenAI usage lower.

## Rebuild Documents

From the repo root:

```bash
python3 admission_data/pipeline/build_rag_documents.py --today 2026-05-19
python3 admission_data/pipeline/dedupe_rag_documents.py
python3 admission_data/pipeline/build_supplemental_rag_documents.py
```

Use the current date for `--today`; it controls deadline/timeline status.

Supplemental sources currently include:

- `data/clean/2026 QS World University Rankings 1.3 (For qs.com) (1).xlsx`
- `data/clean/advice_data.jsonl`

If the combined file has duplicate `doc_id` rows, regenerate the unique embedding input before embedding.

## Embed With OpenAI

Embed the unique document file:

```bash
python3 admission_data/pipeline/embed_rag_documents_openai.py --resume
```

Equivalent explicit command:

```bash
python3 admission_data/pipeline/embed_rag_documents_openai.py \
  --input admission_data/data/clean/rag/rag_documents_openai_unique.jsonl \
  --output admission_data/data/clean/rag/rag_embeddings_openai_3_small.jsonl \
  --model text-embedding-3-small \
  --batch-size 100 \
  --resume
```

The script supports resume mode, so it can continue after rate limits or interruption.

## Build FAISS

Build the local vector store:

```bash
python3 admission_data/pipeline/build_faiss_index.py
```

Equivalent explicit command:

```bash
python3 admission_data/pipeline/build_faiss_index.py \
  --input admission_data/data/clean/rag/rag_embeddings_openai_3_small.jsonl \
  --index admission_data/data/clean/rag/rag_openai_3_small.faiss \
  --metadata admission_data/data/clean/rag/rag_openai_3_small_metadata.jsonl \
  --manifest admission_data/data/clean/rag/rag_openai_3_small_faiss_manifest.json
```

## Smoke Tests

Test retrieval:

```bash
python3 admission_data/pipeline/retrieve_context.py "What is MIT's 2026 QS ranking?" \
  --doc-type university_ranking \
  --limit 3 \
  --search-k 500 \
  --pretty
```

```bash
python3 admission_data/pipeline/retrieve_context.py "What is the study pathway for Germany international students?" \
  --doc-type country_advice \
  --limit 3 \
  --search-k 500 \
  --pretty
```

Test OpenAI chat:

```bash
python3 admission_data/pipeline/openai_rag_chat.py "What is MIT's 2026 QS ranking?" --doc-type university_ranking
```

Run the Streamlit app:

```bash
python3 -m streamlit run admission_data/app_streamlit.py --server.port 8501 --server.address 127.0.0.1
```

## Document Types

- `program`: programs from `data/clean/programs/programs.csv`
- `admission_page`: school admission pages
- `school_page`: general school pages
- `scholarship`: scholarship facts
- `deadline`: application deadline or intake facts
- `tuition`: tuition facts
- `requirement`: eligibility or exam requirement facts
- `university_ranking`: 2026 QS ranking records
- `country_advice`: country-level study pathway advice
- `program_advice`: program-level advising/pathway records

## Metadata

Important metadata fields:

- `doc_id`: stable document key
- `parent_id`: shared key for chunks from the same source row
- `doc_type`: retrieval category
- `school_id`
- `school_name`
- `country`
- `replace_scope`: recommended refresh/delete scope
- `deadline_status`
- `has_stale_date`
- `extracted_dates`
- `build_date`
- `data_status`

Client-facing answers should not reveal source URLs, scrape details, raw IDs, or internal metadata.

## Refresh Rule

When deadlines or facts change, do not only append new chunks.

Recommended process:

1. Update or rebuild the clean source row.
2. Rebuild RAG documents.
3. Regenerate the unique embedding input.
4. Re-embed affected docs, or rebuild the full embedding file.
5. Rebuild FAISS and metadata.

This prevents the retriever from seeing both old and new deadline text.
