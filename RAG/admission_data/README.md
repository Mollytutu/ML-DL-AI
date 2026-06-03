# admission_data

Structured Collegedunia-derived school, admission-page, and program data across `16` countries.

The project has two jobs:
- maintain a scraping and cleanup pipeline under `pipeline/`
- publish stable downstream datasets under `data/clean/`

Best use cases:
- backend search over schools and programs
- consultant workflows
- RAG systems that answer tuition, duration, requirement, and school-level admission questions

## Start Here

- `data/clean/`: current source-of-truth outputs for downstream use
- `pipeline/`: crawl, extraction, merge, and cleanup scripts
- `OUTPUT_REVIEW.md`: current package quality and coverage review
- `pipeline/README.md`: pipeline stages, script ownership, and practical run order
- `data/clean/README.md`: what is intentionally kept in the clean output package
- `data/raw/README.md`: what the small raw folder currently contains

## Folder Map

- `data/clean/programs/`: one-row-per-program output plus program-level QA summaries
- `data/clean/admission_pages/`: school-level admission pages and summaries
- `data/clean/school_pages/`: school-homepage context and merged school facts
- `data/raw/`: lightweight raw URL inventories used as crawl inputs
- `data/raw/pipeline_inputs/`: reviewed school lists plus broader raw crawl inputs used for follow-up pipeline runs
- `pipeline/`: crawler, extraction, aggregation, and export scripts

## Current Counts

- Countries in reviewed school list: `16`
- Reviewed school list rows: `1421`
- Program rows in `programs.csv`: `82,111`
- Schools with programs: `1,418`
- Admission page rows in `admission_pages.csv`: `54,767`
- Schools with admissions: `1,421`
- School-page fact rows in `school_pages.csv`: `48,335`
- Schools with school pages: `1,421`

## Key Output Files

- `data/clean/programs/programs.csv`: generated primary one-row-per-program dataset
- `data/clean/admission_pages/admission_pages.csv`: generated cleaned school-level admission pages
- `data/clean/school_pages/school_pages.csv`: generated school-homepage context layer
- `data/clean/rag/`: generated RAG documents and vector files for the admissions adviser chatbot. Large generated files are not committed to GitHub.

## One School, Three Page Layers

1. `school page`
   Use `data/clean/school_pages/school_pages.csv` for school-homepage context, rankings, highlights, costs, and overview facts.
2. `admission page`
   Use `data/clean/admission_pages/admission_pages.csv` for school-level deadlines, scholarships, tuition, exam requirements, and admission signals.
3. `program page`
   Use `data/clean/programs/programs.csv` for program name, level, duration, important date, tuition, requirements, and exam scores.

## Recommended Retrieval Order

1. `data/clean/programs/programs.csv`
2. `data/clean/admission_pages/admission_pages.csv`
3. `data/clean/school_pages/school_pages.csv`
4. Optional pipeline reference: `data/raw/pipeline_inputs/school_list.csv`

For vector ingestion, generate the RAG documents locally, then embed them with OpenAI or import the vectors into Supabase/pgvector:

```bash
python3 pipeline/build_rag_documents.py --today YYYY-MM-DD
python3 pipeline/dedupe_rag_documents.py
python3 pipeline/build_supplemental_rag_documents.py
python3 pipeline/embed_rag_documents_openai.py --resume
python3 pipeline/build_faiss_index.py
```

## Recommended Join Keys

- Primary school key: `school_id`
- Stable numeric school key: `school_num_id`
- URL join keys: `school_homepage_url` in programs, `admission_url` in admissions, `homepage_url` in `data/raw/pipeline_inputs/school_list.csv`

## Human Collection Rule

- For manual school-page collection, use `data/raw/pipeline_inputs/school_list.csv` as the source of truth.
- Collect school pages from the `homepage_url` values in that file.
- Do not start from ad hoc search results when a school exists in `school_list.csv`.
- Canonical URL rule (strict): all school URLs must live in `data/raw/pipeline_inputs/school_list.csv`.
- Any list under `data/clean/` (including country-sorted lists) must be generated from `school_list.csv`, not used as an independent URL source.

## USA Bachelor Business Scope Note

- Current USA growth workflow is based on website discovery from Collegedunia USA bachelor/business listing pages.
- This scope is tracked in run artifacts named `data/run/reports/us_list_business_new11_*`.
- Use these `us_list_business_new11_*` files as the written reference for that campaign scope before broad multi-country list completion.

## Quick Validation

1. `programs.csv` should have `82,111` rows.
2. `admission_pages.csv` should have `54,767` rows.
3. `school_pages.csv` should have `48,335` rows.
4. `data/raw/pipeline_inputs/school_list.csv` should have `1421` rows.
5. `data/raw/pipeline_inputs/collegedunia_school_seeds_from_raw.csv` is the broader raw crawl inventory used for follow-up reruns.
6. Optional check against internal refresh reports if needed.
7. Inspect one school across all layers with `rg -n "university_of_pittsburgh|University of Pittsburgh" admission_data/data/clean`.

## Local Setup

```bash
cd RAG/admission_data
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

To run the local adviser chatbot, add `OPENAI_API_KEY` to `admission_data/.env`, build or download the vector store, then run:

```bash
python3 -m streamlit run app_streamlit.py --server.port 8501 --server.address 127.0.0.1
```

## Known Limits

- `programs.csv` is the strongest dataset in this project.
- `admission_pages.csv` is useful, but some Collegedunia admission pages still mix in light program-style snippets.
- Some lower-coverage schools have very little or no usable admission information on their Collegedunia `/admission` page.
- `school_pages.csv` is useful school context and should be evaluated together with the current reviewed scrape state.
