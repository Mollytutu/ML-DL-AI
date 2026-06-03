# Pipeline Guide

`pipeline/` contains the working crawl, extraction, merge, and review scripts for `admission_data`.

## Audit

- Every `.py` file in this folder is listed below.
- No clearly retired Python scripts were kept in `pipeline/`.
- `pipeline/__pycache__/` was removed during cleanup.

## Main Flow

1. Discover or refresh school URLs.
2. Build school/program crawl inputs.
3. Build queue batches.
4. Crawl school or program pages.
5. Extract program rows.
6. Build clean program outputs.
7. Build clean admission-page outputs.
8. Merge clean school-page outputs.

## Harness Agent Contract (Authoritative)

Use this section as the operational contract for the scraping agents.

### Agent Roles

1. `scrape_agent`
   Runs one queue target through `run_retry_queue_once.py` (school page, admission page, programs).
2. `quality_check_agent`
   Validates quality gates and integrity after each scrape cycle.

### Mission / Goal

For each school URL in queue:

1. Scrape comprehensive `school_summary` and `admission_summary` content (expand Read More sections).
2. Keep `school_id` consistent with `data/raw/pipeline_inputs/school_list.csv`.
3. Append only into existing clean outputs (no ad-hoc clean-file creation).
4. Pass quality checks before moving forward.

### Success Criteria

1. Summary length:
   - high traffic school: `school_summary >= 800` words
   - low traffic school: `school_summary >= 300` words
2. Admission facts and school facts meet configured thresholds.
3. `school_id` in clean admission/school tables maps to `school_list.csv`.
4. No banned text patterns in target outputs (`india`, `inr`, `lakh`, etc., per user rule).

### Where Logs Are

1. Harness run events:
   - `data/run/reports/harness_run_log.jsonl`
2. Mistakes / failed quality reasons:
   - `data/run/reports/harness_mistakes.log`
3. Session memory / non-negotiable rules:
   - `data/run/reports/agent_session_state.txt`
4. Per-run scrape artifacts:
   - `data/run/reports/retry_queue_runs/<timestamp>/`

### Standard Run Command (Base Rule)

```bash
MIN_SUCCESS_PER_WINDOW=30 WINDOW_MINUTES=30 CHECK_EVERY_SECONDS=60 FAIL_ON_QUALITY_FAIL=0 \
admission_data/pipeline/run_with_sla_guard.sh "admission_data/data/run/reports/shards_all/all_q_*"
```

Base rule:
1. Scraper must keep running until queues are empty.
2. `quality_check_agent` failures are logged and requeued by default; set `FAIL_ON_QUALITY_FAIL=1` for strict stop-on-first-failure mode.
3. If throughput is below 30 successful schools per 30 minutes, stop immediately and alert.

### How Agent Decides Next Step

1. `quality_pass=true`: mark target successful and pop from queue.
2. `quality_pass=false`: write mistake log, keep queue progression, and continue by default.
3. Requeue behavior is configured to avoid silent skip-forward on failed targets.

### State-Locked Command (Preferred)

Use this when `agent_session_state.txt` has the locked order rules:
1) `us_never_scraped_queue` first
2) then summary-only backfill for `school_list_missing_any_queue`

```bash
admission_data/pipeline/run_state_locked_flow.sh
```

## Inventory

### Discovery

- `discover_urls.py`
  Utility. Sitemap-driven URL discovery.
- `discover_links_selenium.py`
  Utility. Selenium-based link discovery.
- `filter_school_urls.py`
  Utility. Filters URL inventories to school targets.
- `export_school_urls.py`
  Utility. Exports deduplicated school URLs.
- `export_school_list.py`
  Utility. Builds the reviewed school list.
- `split_school_list_by_country.py`
  Utility. Splits the school list by country.
- `extract_school_program_seeds.py`
  Utility. Builds school/program/subunit crawl-input tables.
- `discover_usa_school_homepages_via_search.py`
  Utility. Uses search-index queries to discover additional USA Collegedunia school homepage URLs when direct site crawling is blocked. Supports credit-saving controls such as query checkpoint logs (`--query-log-csv`), block-streak early stop (`--stop-on-block-streak`), and batched offsets/limits.
- `run_discovery_with_healthcheck.py`
  Wrapper utility. Runs preflight DNS/smoke checks and automatically chooses direct Selenium (`undetected_chromedriver`) or search-index fallback mode.
- `run_scheduler.py`
  Utility. Daily scheduler for pipeline jobs from JSON config (`scheduler_jobs.example.json`) with lock file protection, state tracking, and per-run log files.
- `run_retry_queue_once.py`
  Utility (`scrape_agent`). Processes one URL from a retry queue (`school + admission + program`), merges clean outputs, and rotates queue state for scheduler-driven incremental retries.
- `run_scrape_harness.py`
  Utility (`harness framework`). Enforces two-agent execution:
  1) `scrape_agent` runs `run_retry_queue_once.py`.
  2) `quality_check_agent` validates quality gates, school_id consistency, and token filters; logs failures into harness mistake logs.
- `scheduler_jobs.example.json`
  Utility config template. Example timed jobs for safe U.S. discovery and optional program merge.
- `scheduler_jobs.local.json`
  Local utility config. Example interval-driven retry job (`every_minutes`) for incremental U.S. queue processing.
- `merge_school_seed_urls.py`
  Utility. Merges confirmed school homepage URLs into school seed CSVs while preserving existing numbering and assigning new `school_num_id` values.
- `refresh_school_seed_inventory.py`
  Utility. Refreshes the broader raw school inventory from raw URL lists while preserving existing `school_num_id` values and filtering duplicate school variants.
- `build_school_program_queues.py`
  Core. Builds queue CSV/TXT/JSONL batches from school and program inputs.

### Crawl

- `scrape_collegedunia_selenium.py`
  Core. Default Selenium crawler.
- `scrape_collegedunia_playwright.py`
  Alternate. Playwright crawler variant.
- `run_collegedunia_queue_batches.py`
  Core. Runs queue batches through the selected crawler.
- `crawl_and_merge_remaining_school_homepages.py`
  Wrapper. Refreshes school-homepage coverage and merges it into `data/clean/school_pages/`.
- `crawl_and_merge_program_details.py`
  Wrapper. Rebuilds program queues, crawls remaining program targets, and rebuilds program outputs.

### Extraction And Build

- `extract_program_cards.py`
  Core. Extracts one structured row per program card.
- `run_program_card_batches.py`
  Runner. Parallel batch runner for `extract_program_cards.py`.
- `build_school_program_tables.py`
  Core. Builds `programs.csv` and related program/school summary tables.
- `build_clean_admissions.py`
  Core. Builds `data/clean/admission_pages/` from raw `/admission` crawl output.
- `aggregate_by_school.py`
  Helper. Aggregates raw pages and facts by school.
- `merge_clean_school_facts.py`
  Core. Merges school-page outputs into reviewed `school_pages.csv`.
- `build_country_school_summary.py`
  Reporting. Builds the country summary CSV used for review work.

### Shared Modules

- `csv_safety.py`
  Shared CSV cleanup and normalization helpers.
- `collegedunia_paths.py`
  Shared URL and path helpers.

## Inputs And Outputs

- Reviewed school list: `data/raw/pipeline_inputs/school_list.csv`
- Broader raw school inventory: `data/raw/pipeline_inputs/collegedunia_school_seeds_from_raw.csv`
- Program inputs: `data/raw/pipeline_inputs/collegedunia_program_seeds_from_raw.csv`
- Main outputs: `data/clean/programs/`, `data/clean/admission_pages/`, `data/clean/school_pages/`

## Keep Out Of This Folder

- generated crawl outputs
- archive copies
- scratch files
- clean-package deliverables
- `__pycache__/`
- `*.pyc`
