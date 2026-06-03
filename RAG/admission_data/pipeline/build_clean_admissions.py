import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

from csv_safety import clean_local_currency_text, normalize_audience_text, sanitize_row


NOISE_EXACT_VALUES = {
    "1 on 1 Interaction",
    "Practice Questions",
    "Courses & Fees",
    "Highest fees",
    "The request could not be satisfied.",
    "Entry Requirement:",
    "established year",
    "Degrees Available:",
    "Average Fees",
}
NOISE_VALUE_RE = re.compile(
    r"(content curator|updated\s+\d|do you think the fees are wrong|top degrees:|practice questions|1 on 1 interaction)",
    re.I,
)
PROGRAM_SNIPPET_RE = re.compile(r"\(\s*\d+(?:\.\d+)?[Kk]?\s+Views?(?:\s+Last\s+Year)?\s*\)", re.I)
ERROR_TITLES = {"ERROR: The request could not be satisfied"}
ERROR_H1S = {"404", "403 ERROR"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Merge and clean admission-only crawl outputs into final admissions CSVs.")
    p.add_argument("--crawl-dir", default="data/run/admission_729/crawled_admission_only")
    p.add_argument("--out-dir", default="data/clean/admission_pages")
    return p.parse_args()


def load_csv_rows(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as f:
            rows.extend(csv.DictReader(f))
    return rows


def keep_page(row: dict) -> bool:
    if (row.get("status_code") or "") != "200":
        return False
    if (row.get("page_type") or "").strip().lower() != "admission":
        return False
    if (row.get("h1") or "").strip() in ERROR_H1S:
        return False
    if (row.get("title") or "").strip() in ERROR_TITLES:
        return False
    if int(row.get("fact_count") or 0) <= 2:
        return False
    return True


def clean_fact_value(row: dict) -> str:
    value = normalize_audience_text(clean_local_currency_text(row.get("fact_value") or ""))
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ""
    if value in NOISE_EXACT_VALUES:
        return ""
    if NOISE_VALUE_RE.search(value):
        return ""
    if PROGRAM_SNIPPET_RE.search(value):
        return ""
    if re.fullmatch(r"[A-Za-z][A-Za-z\s-]*:", value):
        return ""
    return value


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(sanitize_row(row, fieldnames))


def load_school_maps(paths: list[Path]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_id: dict[str, dict] = {}
    by_homepage: dict[str, dict] = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            canonical = {
                "school_num_id": row.get("school_num_id", ""),
                "school_name": row.get("school_name", ""),
            }
            school_id = row.get("school_id", "")
            if school_id:
                by_id[school_id] = canonical
            homepage_url = row.get("homepage_url", "").rstrip("/")
            if homepage_url:
                by_homepage[homepage_url] = canonical
    return by_id, by_homepage


def main() -> None:
    args = parse_args()
    root = Path(args.crawl_dir)
    out_dir = Path(args.out_dir)
    school_map, homepage_map = load_school_maps(
        [
            Path("data/raw/pipeline_inputs/collegedunia_school_seeds_from_raw.csv"),
            Path("data/raw/pipeline_inputs/school_list.csv"),
        ]
    )
    page_paths = sorted(root.glob("admission_*_pages.csv"))
    fact_paths = sorted(root.glob("admission_*_facts.csv"))
    if not page_paths or not fact_paths:
        raise SystemExit(f"no admission batch CSVs found in {root}")

    page_rows = load_csv_rows(page_paths)
    fact_rows = load_csv_rows(fact_paths)

    kept_pages = [row for row in page_rows if keep_page(row)]
    kept_urls = {row["url"] for row in kept_pages if row.get("url")}

    cleaned_facts: list[dict] = []
    seen_facts: set[tuple[str, str, str]] = set()
    for row in fact_rows:
        url = row.get("url") or ""
        if url not in kept_urls:
            continue
        value = clean_fact_value(row)
        if not value:
            continue
        row = dict(row)
        row["fact_value"] = value
        key = (row.get("school_id") or "", row.get("fact_key") or "", value)
        if key in seen_facts:
            continue
        seen_facts.add(key)
        cleaned_facts.append(row)

    merged_pages = out_dir / "admission_pages_merged.csv"
    merged_facts = out_dir / "admission_facts_merged.csv"
    admission_summary = out_dir / "admission_summary.csv"
    admission_facts = out_dir / "admission_pages.csv"
    temp_school_summary = out_dir / "_temp_school_summary.csv"
    temp_school_facts = out_dir / "_temp_school_facts.csv"
    temp_school_summary_jsonl = out_dir / "_temp_school_summary.jsonl"

    page_fieldnames = list(page_rows[0].keys())
    fact_fieldnames = list(fact_rows[0].keys())
    write_csv(merged_pages, kept_pages, page_fieldnames)
    write_csv(merged_facts, cleaned_facts, fact_fieldnames)

    cmd = [
        sys.executable,
        "pipeline/aggregate_by_school.py",
        "--pages-csv",
        str(merged_pages),
        "--facts-csv",
        str(merged_facts),
        "--summary-csv",
        str(temp_school_summary),
        "--school-facts-csv",
        str(temp_school_facts),
        "--admission-summary-csv",
        str(admission_summary),
        "--admission-facts-csv",
        str(admission_facts),
        "--min-pages-per-school",
        "1",
    ]
    subprocess.run(cmd, check=True)

    for csv_path in [admission_summary, admission_facts]:
        with csv_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
            fieldnames = list(rows[0].keys()) if rows else []
        for row in rows:
            canonical = school_map.get(row.get("school_id") or "", {})
            if not canonical:
                admission_url = (row.get("admission_url") or "").rstrip("/")
                homepage_url = admission_url.rsplit("/admission", 1)[0] if admission_url.endswith("/admission") else ""
                canonical = homepage_map.get(homepage_url, {})
            if canonical.get("school_num_id"):
                row["school_num_id"] = canonical["school_num_id"]
            if canonical.get("school_name"):
                row["school_name_guess"] = canonical["school_name"]
        if fieldnames:
            write_csv(csv_path, rows, fieldnames)

    for path in [temp_school_summary, temp_school_facts, temp_school_summary_jsonl]:
        if path.exists():
            path.unlink()

    summary = {
        "raw_pages": len(page_rows),
        "kept_pages": len(kept_pages),
        "raw_facts": len(fact_rows),
        "kept_facts": len(cleaned_facts),
    }
    summary_path = out_dir / "admission_build_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"admission_summary_csv={admission_summary}")
    print(f"admission_pages_csv={admission_facts}")


if __name__ == "__main__":
    main()
