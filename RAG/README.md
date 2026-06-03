# RAG Admissions Advisor

An end-to-end AI data project for building a retrieval-augmented admissions advisor from web-scraped education data.

The project collects school, admission, and program information from Collegedunia-style pages, cleans it into structured CSV datasets, converts the clean tables into RAG documents, embeds them with the OpenAI API, builds a local FAISS vector index, and serves answers through a Streamlit chatbot.

## What This Shows

- Web scraping with Selenium and Playwright
- URL discovery, queue batching, retry flows, and scrape quality checks
- Data cleaning, deduplication, normalization, and school/program joins
- Structured education datasets for schools, admission pages, and program pages
- RAG document generation from cleaned tabular data
- OpenAI embedding API integration
- FAISS vector search for local semantic retrieval
- Chatbot answer generation using retrieved admissions context
- Portfolio-ready pipeline design with reproducible scripts and clear run order

## Project Folder

The main project is in [`admission_data/`](./admission_data/).

Key files:

- [`admission_data/app_streamlit.py`](./admission_data/app_streamlit.py): Streamlit admissions advisor chatbot
- [`admission_data/pipeline/`](./admission_data/pipeline/): scraping, cleaning, RAG, embedding, and vector-index scripts
- [`admission_data/pipeline/README.md`](./admission_data/pipeline/README.md): pipeline run guide and script inventory
- [`admission_data/data/clean/README.md`](./admission_data/data/clean/README.md): clean data package notes
- [`admission_data/data/clean/rag/README.md`](./admission_data/data/clean/rag/README.md): generated RAG artifact guide

## Architecture

```text
School/program URLs
        |
        v
Selenium / Playwright crawlers
        |
        v
Raw page and fact CSVs
        |
        v
Cleaning + aggregation scripts
        |
        v
Clean school, admission, and program tables
        |
        v
RAG document builder + deduper
        |
        v
OpenAI embeddings
        |
        v
FAISS vector index
        |
        v
Streamlit admissions advisor
```

## Dataset Scope

Current local pipeline outputs were built around:

- 16 countries
- 1,421 reviewed schools
- 82,111 program rows
- 54,767 admission-page rows
- 48,335 school-page fact rows

The full generated datasets and vector files are intentionally not all committed here because some artifacts are multiple gigabytes. The repository keeps the source code, run instructions, lightweight metadata, and smaller reference files so the pipeline can be rebuilt locally.

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
- The OpenAI API is used for embeddings and answer generation.
- FAISS is used for local vector retrieval; the same documents can also be moved into a hosted vector database such as pgvector or Supabase.
