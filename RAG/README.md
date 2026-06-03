# RAG Admissions Advisor

This is an end-to-end AI project that shows how I can build a practical retrieval-augmented generation system from raw web data to a working chatbot.

The project scrapes university and admissions information, cleans it into structured datasets, transforms the clean data into RAG documents, embeds those documents with the OpenAI API, builds a FAISS vector index, and serves answers through a Streamlit admissions advisor.

## Hiring Manager Summary

This project demonstrates that I can:

- scrape and organize real-world data from public web pages
- clean messy HTML-derived records into structured CSV datasets
- design repeatable data pipelines with queue batching, retries, and quality checks
- create retrieval-ready documents from structured data
- use the OpenAI API for embeddings and LLM answers
- build and search a local FAISS vector index
- ship a usable AI app interface with Streamlit
- keep large generated artifacts out of Git while documenting how to rebuild them

## Project Scale

- 16 countries
- 1,421 reviewed schools
- 82,111 program rows
- 54,767 admission-page rows
- 48,335 school-page fact rows

The full generated embeddings and FAISS files are multiple gigabytes, so this repository contains the source code, documentation, lightweight metadata, and smaller reference files. The large RAG artifacts can be rebuilt locally from the pipeline.

## AI System Architecture

```text
Public school and program pages
        |
        v
Selenium / Playwright scraping
        |
        v
Raw page text and extracted facts
        |
        v
Cleaning, deduplication, normalization
        |
        v
Structured school, admission, and program tables
        |
        v
RAG document generation
        |
        v
OpenAI embeddings
        |
        v
FAISS vector index
        |
        v
Streamlit admissions advisor chatbot
```

## What Is Inside

- [`admission_data/app_streamlit.py`](./admission_data/app_streamlit.py): Streamlit chatbot interface
- [`admission_data/pipeline/`](./admission_data/pipeline/): scraping, cleaning, embedding, retrieval, and RAG scripts
- [`admission_data/pipeline/README.md`](./admission_data/pipeline/README.md): detailed pipeline guide
- [`admission_data/data/clean/README.md`](./admission_data/data/clean/README.md): clean data package notes
- [`admission_data/data/clean/rag/README.md`](./admission_data/data/clean/rag/README.md): RAG artifact and rebuild notes

## Technical Highlights

- Web scraping: Selenium, Playwright
- Data engineering: CSV normalization, school/program joins, deduplication, coverage reporting
- RAG: document construction, supplemental documents, dedupe manifests
- Embeddings: OpenAI embedding API
- Retrieval: FAISS semantic search
- App: Streamlit chatbot with admission-focused answer behavior

## Run Locally

```bash
cd RAG/admission_data
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Add your OpenAI key:

```bash
export OPENAI_API_KEY="your_api_key"
```

Build RAG documents and vectors:

```bash
python3 pipeline/build_rag_documents.py --today YYYY-MM-DD
python3 pipeline/dedupe_rag_documents.py
python3 pipeline/build_supplemental_rag_documents.py
python3 pipeline/embed_rag_documents_openai.py --resume
python3 pipeline/build_faiss_index.py
```

Run the chatbot:

```bash
python3 -m streamlit run app_streamlit.py --server.port 8501 --server.address 127.0.0.1
```

## Notes

- `.env`, virtual environments, runtime logs, raw scrape runs, generated JSONL embeddings, and FAISS indexes are excluded from Git.
- The same cleaned RAG documents could be served through a backend API or moved into a hosted vector database such as pgvector or Supabase.
- The goal of this project is to show practical AI product engineering, not only prompt experimentation.
