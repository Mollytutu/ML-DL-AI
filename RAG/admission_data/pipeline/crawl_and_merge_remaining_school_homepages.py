import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

from csv_safety import sanitize_row

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else PROJECT_ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the remaining-school homepage crawl with Selenium and merge the results back into the clean school-pages workflow."
    )
    parser.add_argument(
        "--queue-root",
        default="data/clean/queues/remaining_school_homepages_312",
        help="Directory containing the remaining school homepage queue files.",
    )
    parser.add_argument(
        "--crawl-output-dir",
        default="data/clean/queues/remaining_school_homepages_312/crawled",
        help="Directory to write Selenium crawl batch outputs.",
    )
    parser.add_argument(
        "--summary-csv",
        default="data/run/reports/remaining_school_homepages_312_summary.csv",
        help="Aggregated summary CSV for the remaining-school crawl.",
    )
    parser.add_argument(
        "--school-facts-csv",
        default="data/clean/school_pages/remaining_school_homepages_312_school_facts.csv",
        help="Aggregated school-pages CSV for the remaining-school crawl.",
    )
    parser.add_argument(
        "--admission-summary-csv",
        default="data/clean/admission_pages/admission_summary.csv",
        help="Aggregated admission summary CSV for the remaining-school crawl.",
    )
    parser.add_argument(
        "--admission-facts-csv",
        default="data/clean/admission_pages/admission_pages.csv",
        help="Aggregated admission facts CSV for the remaining-school crawl.",
    )
    parser.add_argument(
        "--coverage-summary",
        default="data/clean/queues/remaining_school_homepages_312/coverage_after_merge.json",
        help="Coverage summary written after the reviewed merge completes.",
    )
    parser.add_argument("--skip-crawl", action="store_true", help="Skip Selenium crawling and only merge existing crawl outputs.")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", dest="headless", action="store_false")
    parser.add_argument("--driver-path", default=None)
    parser.add_argument("--browser-binary", default=None)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--wait-sec", type=float, default=3.0)
    parser.add_argument("--min-pages-per-school", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run_command(cmd: list[str], dry_run: bool = False) -> None:
    print(" ".join(cmd))
    if not dry_run:
        subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)


def merge_csv_files(input_paths: list[Path], output_path: Path) -> int:
    rows_written = 0
    fieldnames: list[str] = []
    for path in input_paths:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not fieldnames:
                fieldnames = reader.fieldnames or []
                output_path.parent.mkdir(parents=True, exist_ok=True)
                out_handle = output_path.open("w", newline="", encoding="utf-8")
                writer = csv.DictWriter(out_handle, fieldnames=fieldnames)
                writer.writeheader()
            else:
                writer = csv.DictWriter(out_handle, fieldnames=fieldnames)
            for row in reader:
                writer.writerow(sanitize_row({key: row.get(key, "") for key in fieldnames}, fieldnames))
                rows_written += 1
    if not fieldnames:
        raise SystemExit(f"no CSV rows found for {output_path.name}")
    out_handle.close()
    return rows_written


def institution_key(url: str) -> tuple[str, str] | None:
    match = re.search(r"https?://[^/]+/([^/]+)/[^/]+/(\d+)-", (url or "").strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def write_coverage_summary(clean_list_path: Path, merged_facts_path: Path, out_path: Path) -> None:
    with clean_list_path.open(newline="", encoding="utf-8") as handle:
        clean_rows = list(csv.DictReader(handle))
    with merged_facts_path.open(newline="", encoding="utf-8") as handle:
        merged_rows = list(csv.DictReader(handle))

    clean_keys = {institution_key(row["homepage_url"]) for row in clean_rows if institution_key(row["homepage_url"])}
    merged_keys = {
        (row["country"], row["institution_numeric_id"])
        for row in merged_rows
        if row.get("country") and row.get("institution_numeric_id")
    }

    summary = {
        "target_school_rows": len(clean_rows),
        "covered_institutions": len(clean_keys & merged_keys),
        "remaining_rows": len([row for row in clean_rows if institution_key(row["homepage_url"]) not in merged_keys]),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main() -> None:
    args = parse_args()
    queue_root = resolve_path(args.queue_root)
    crawl_output_dir = resolve_path(args.crawl_output_dir)
    summary_csv = resolve_path(args.summary_csv)
    school_facts_csv = resolve_path(args.school_facts_csv)
    coverage_summary = resolve_path(args.coverage_summary)

    queue_dir = queue_root / "school_homepage_queue_batches"
    progress_file = queue_root / "school_homepage_queue_progress.json"
    merged_pages_csv = crawl_output_dir / "school_homepage_merged_pages.csv"
    merged_facts_csv = crawl_output_dir / "school_homepage_merged_facts.csv"

    if not args.skip_crawl:
        crawl_cmd = [
            sys.executable,
            "pipeline/run_collegedunia_queue_batches.py",
            "--queue-dir",
            str(queue_dir),
            "--output-dir",
            str(crawl_output_dir),
            "--scraper",
            "pipeline/scrape_collegedunia_selenium.py",
            "--page-prefix",
            "school_homepage",
            "--fact-prefix",
            "school_homepage",
            "--progress-file",
            str(progress_file),
            "--wait-sec",
            str(args.wait_sec),
            "--facts-mode",
            "school_homepage",
        ]
        if args.max_pages > 0:
            crawl_cmd.extend(["--max-pages", str(args.max_pages)])
        if args.headless:
            crawl_cmd.append("--headless")
        else:
            crawl_cmd.append("--no-headless")
        if args.driver_path:
            crawl_cmd.extend(["--driver-path", args.driver_path])
        if args.browser_binary:
            crawl_cmd.extend(["--browser-binary", args.browser_binary])
        if args.dry_run:
            crawl_cmd.append("--dry-run")
        run_command(crawl_cmd, dry_run=args.dry_run)
        if args.dry_run:
            return

    page_parts = sorted(crawl_output_dir.glob("school_homepage_*_pages.csv"))
    fact_parts = sorted(crawl_output_dir.glob("school_homepage_*_facts.csv"))
    if not page_parts or not fact_parts:
        raise SystemExit(f"no crawl CSV outputs found in {crawl_output_dir}")

    page_rows = merge_csv_files(page_parts, merged_pages_csv)
    fact_rows = merge_csv_files(fact_parts, merged_facts_csv)
    print(f"merged_pages_rows={page_rows}")
    print(f"merged_facts_rows={fact_rows}")

    aggregate_cmd = [
        sys.executable,
        "pipeline/aggregate_by_school.py",
        "--pages-csv",
        str(merged_pages_csv),
        "--facts-csv",
        str(merged_facts_csv),
            "--summary-csv",
            str(summary_csv),
            "--school-facts-csv",
            str(school_facts_csv),
            "--admission-summary-csv",
            str(resolve_path(args.admission_summary_csv)),
            "--admission-facts-csv",
            str(resolve_path(args.admission_facts_csv)),
            "--min-pages-per-school",
            str(args.min_pages_per_school),
        ]
    run_command(aggregate_cmd, dry_run=args.dry_run)

    canonical_merge_cmd = [
        sys.executable,
        "pipeline/merge_clean_school_facts.py",
    ]
    run_command(canonical_merge_cmd, dry_run=args.dry_run)

    if not args.dry_run:
        write_coverage_summary(
            clean_list_path=resolve_path("data/raw/pipeline_inputs/school_list.csv"),
            merged_facts_path=resolve_path("data/clean/school_pages/school_pages.csv"),
            out_path=coverage_summary,
        )


if __name__ == "__main__":
    main()
