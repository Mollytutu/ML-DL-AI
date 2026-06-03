import argparse
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else PROJECT_ROOT / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build program queues, crawl them with Selenium, and write school/program outputs."
    )
    parser.add_argument(
        "--workspace-root",
        default="data/run/program_details_2026",
        help="Temporary workspace for queues and crawl outputs.",
    )
    parser.add_argument(
        "--school-list-csv",
        default="data/raw/pipeline_inputs/collegedunia_school_seeds_from_raw.csv",
        help="Broader raw school seed list used to seed school/program queue generation.",
    )
    parser.add_argument(
        "--program-seeds-csv",
        default="data/raw/pipeline_inputs/collegedunia_program_seeds_from_raw.csv",
        help="Program seed table used to build the crawl queues.",
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--wait-sec", type=float, default=3.0)
    parser.add_argument("--max-pages", type=int, default=0)
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", dest="headless", action="store_false")
    parser.add_argument("--driver-path", default=None)
    parser.add_argument("--browser-binary", default=None)
    parser.add_argument(
        "--queue-kinds",
        nargs="+",
        default=["program_detail", "program_index"],
        help="Program queue kinds to crawl.",
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-crawl", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run_command(cmd: list[str], dry_run: bool = False) -> None:
    print(" ".join(cmd))
    if not dry_run:
        subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)


def main() -> None:
    args = parse_args()
    workspace_root = resolve_path(args.workspace_root)
    queue_root = workspace_root / "queues"
    crawl_output_dir = workspace_root / "crawled"
    clean_programs_dir = resolve_path("data/clean/programs")
    queue_root.mkdir(parents=True, exist_ok=True)
    crawl_output_dir.mkdir(parents=True, exist_ok=True)
    clean_programs_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_build:
        build_cmd = [
            sys.executable,
            "pipeline/build_school_program_queues.py",
            "--school-list-csv",
            str(resolve_path(args.school_list_csv)),
            "--program-seeds-csv",
            str(resolve_path(args.program_seeds_csv)),
            "--out-dir",
            str(queue_root),
            "--batch-size",
            str(args.batch_size),
        ]
        run_command(build_cmd, dry_run=args.dry_run)
        if args.dry_run:
            return

    if not args.skip_crawl:
        for queue_kind in args.queue_kinds:
            queue_dir = queue_root / f"{queue_kind}_queue_batches"
            progress_file = queue_root / f"{queue_kind}_queue_progress.json"
            output_dir = crawl_output_dir / queue_kind
            output_dir.mkdir(parents=True, exist_ok=True)
            crawl_cmd = [
                sys.executable,
                "pipeline/run_collegedunia_queue_batches.py",
                "--queue-dir",
                str(queue_dir),
                "--output-dir",
                str(output_dir),
                "--scraper",
                "pipeline/scrape_collegedunia_selenium.py",
                "--page-prefix",
                queue_kind,
                "--fact-prefix",
                queue_kind,
                "--wait-sec",
                str(args.wait_sec),
                "--max-pages",
                str(args.max_pages),
                "--facts-mode",
                "all",
                "--progress-file",
                str(progress_file),
            ]
            if args.headless:
                crawl_cmd.append("--headless")
            else:
                crawl_cmd.append("--no-headless")
            if args.driver_path:
                crawl_cmd.extend(["--driver-path", args.driver_path])
            if args.browser_binary:
                crawl_cmd.extend(["--browser-binary", args.browser_binary])
            run_command(crawl_cmd, dry_run=args.dry_run)
            if args.dry_run:
                return

    page_parts = []
    fact_parts = []
    for queue_kind in args.queue_kinds:
        queue_output_dir = crawl_output_dir / queue_kind
        page_parts.extend(sorted(queue_output_dir.glob(f"{queue_kind}_*_pages.csv")))
        fact_parts.extend(sorted(queue_output_dir.glob(f"{queue_kind}_*_facts.csv")))
    if not page_parts or not fact_parts:
        raise SystemExit(f"no crawl CSV outputs found in {crawl_output_dir}")

    merged_pages_csv = crawl_output_dir / "program_merged_pages.csv"
    merged_facts_csv = crawl_output_dir / "program_merged_facts.csv"

    # Merge batch outputs in-place before aggregation.
    import csv

    def merge_csv_files(input_paths: list[Path], output_path: Path) -> int:
        rows_written = 0
        fieldnames: list[str] = []
        out_handle = None
        try:
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
                        writer.writerow({key: row.get(key, "") for key in fieldnames})
                        rows_written += 1
        finally:
            if out_handle:
                out_handle.close()
        if not fieldnames:
            raise SystemExit(f"no CSV rows found for {output_path.name}")
        return rows_written

    page_rows = merge_csv_files(page_parts, merged_pages_csv)
    fact_rows = merge_csv_files(fact_parts, merged_facts_csv)
    print(f"merged_pages_rows={page_rows}")
    print(f"merged_facts_rows={fact_rows}")

    split_cmd = [
        sys.executable,
        "pipeline/build_school_program_tables.py",
        "--pages-csv",
        str(merged_pages_csv),
        "--facts-csv",
        str(merged_facts_csv),
        "--school-summary-csv",
        str(clean_programs_dir / "program_school_summary.csv"),
        "--school-facts-csv",
        str(clean_programs_dir / "program_school_facts.csv"),
        "--program-summary-csv",
        str(workspace_root / "program_summary.csv"),
        "--program-facts-csv",
        str(clean_programs_dir / "program_facts.csv"),
    ]
    run_command(split_cmd, dry_run=args.dry_run)

    if not args.dry_run:
        shutil.rmtree(workspace_root, ignore_errors=True)


if __name__ == "__main__":
    main()
