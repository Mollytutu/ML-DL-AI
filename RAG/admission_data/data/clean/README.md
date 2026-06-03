# Clean Output Folder

This folder is the current clean output set for the `admission_data` pipeline.

## Structure

- root
- `school_pages/`
  - merged school-homepage export: `school_pages.csv`
  - school-homepage facts only, with INR/₹ rows removed
- `admission_pages/`
  - school admission-page output
- `programs/`
  - program-level outputs with `program_level` normalized to `undergrad`, `master`, `phd`, or `certificate`
- `rag/`
  - JSONL documents generated from the clean CSVs for vector ingestion
  - includes stable document IDs, source metadata, and stale deadline flags

## Kept On Purpose

- Canonical school fact exports needed for downstream RAG / embedding work
- Admission-page exports needed for school-wide detail and deadlines
- Program crawl outputs needed for course coverage and review
- RAG ingestion outputs that can be rebuilt from the clean CSV package

## Removed From The Old `processed/` Folder

- Batch-level page and fact CSVs
- Sample, test, tmp, and one-off probe outputs
- Older report versions
- Derived ranking and by-country convenience exports
- Superseded queue directories and staging artifacts

Use this folder as the current source of truth for generated outputs.
