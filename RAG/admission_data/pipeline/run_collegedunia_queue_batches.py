import argparse
import json
import os
import subprocess
import sys
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def chunked(items: list[str], size: int) -> list[list[str]]:
    size = max(1, size)
    return [items[i : i + size] for i in range(0, len(items), size)]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Collegedunia scraper over a directory of queue txt batches")
    p.add_argument("--queue-dir", required=True, help="Directory containing .txt queue batches")
    p.add_argument("--output-dir", required=True, help="Directory to write per-batch CSV outputs")
    p.add_argument("--scraper", default="pipeline/scrape_collegedunia_selenium.py", help="Scraper script to invoke")
    p.add_argument("--page-prefix", required=True, help="Prefix for per-batch pages CSV names")
    p.add_argument("--fact-prefix", required=True, help="Prefix for per-batch facts CSV names")
    p.add_argument("--max-pages", type=int, default=0, help="Optional max pages per batch")
    p.add_argument("--wait-sec", type=float, default=3.0)
    p.add_argument("--facts-mode", choices=["all", "school_homepage"], default="all", help="Which page types should produce extracted facts")
    p.add_argument("--crawl-depth", type=int, default=None, help="Optional crawl depth to pass through to the scraper")
    p.add_argument("--max-child-links-per-page", type=int, default=None, help="Optional max child links per page to pass through to the scraper")
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--no-headless", dest="headless", action="store_false")
    p.add_argument("--driver-path", default=None)
    p.add_argument("--browser-binary", default=None)
    p.add_argument("--progress-file", default=None, help="Optional JSON progress tracker to update after each batch")
    p.add_argument("--parallelism", type=int, default=1, help="Run this many urls from each batch in parallel")
    p.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    return p.parse_args()


def load_progress(path: Path | None) -> dict | None:
    if not path or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_progress(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def build_scrape_cmd(args: argparse.Namespace, urls_file: Path, pages_csv: Path, facts_csv: Path) -> list[str]:
    cmd = [
        sys.executable,
        args.scraper,
        "--urls-file",
        str(urls_file),
        "--pages-csv",
        str(pages_csv),
        "--facts-csv",
        str(facts_csv),
        "--wait-sec",
        str(args.wait_sec),
        "--facts-mode",
        args.facts_mode,
        "--max-pages",
        str(args.max_pages),
    ]
    if args.crawl_depth is not None:
        cmd.extend(["--crawl-depth", str(args.crawl_depth)])
    if args.max_child_links_per_page is not None:
        cmd.extend(["--max-child-links-per-page", str(args.max_child_links_per_page)])
    if args.headless:
        cmd.append("--headless")
    else:
        cmd.append("--no-headless")
    if args.driver_path:
        cmd.extend(["--driver-path", args.driver_path])
    if args.browser_binary:
        cmd.extend(["--browser-binary", args.browser_binary])
    return cmd


def run_one_scrape(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def merge_csvs(csv_paths: list[Path], out_path: Path) -> None:
    import csv as _csv

    rows = []
    header = None
    for csv_path in csv_paths:
        if not csv_path.exists():
            continue
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = _csv.DictReader(fh)
            if header is None:
                header = reader.fieldnames or []
            rows.extend(list(reader))
    if header is None:
        return
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = _csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    queue_dir = Path(args.queue_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_path = Path(args.progress_file) if args.progress_file else None
    progress_state = load_progress(progress_path)

    batch_files = sorted(queue_dir.glob("*.txt"))
    if not batch_files:
        raise SystemExit(f"no .txt batch files found in {queue_dir}")

    for idx, batch_path in enumerate(batch_files, start=1):
        if progress_state and idx not in progress_state.get("pending_batches", []) and idx in progress_state.get("completed_batches", []):
            print(f"[{idx}/{len(batch_files)}] {batch_path.name} already completed, skipping")
            continue

        pages_csv = out_dir / f"{args.page_prefix}_{idx:03d}_pages.csv"
        facts_csv = out_dir / f"{args.fact_prefix}_{idx:03d}_facts.csv"

        urls = [u.strip() for u in batch_path.read_text(encoding="utf-8").splitlines() if u.strip()]
        parallelism = max(1, int(args.parallelism or 1))
        print(f"[{idx}/{len(batch_files)}] {batch_path.name} urls={len(urls)} parallelism={parallelism}", flush=True)
        if args.dry_run:
            cmd = build_scrape_cmd(args, batch_path, pages_csv, facts_csv)
            print(" ".join(cmd), flush=True)
            continue

        if parallelism <= 1 or len(urls) <= 1:
            cmd = build_scrape_cmd(args, batch_path, pages_csv, facts_csv)
            print(" ".join(cmd), flush=True)
            subprocess.run(cmd, check=True)
        else:
            tmpdir = tempfile.mkdtemp(prefix=f"batch_{idx:03d}_split_")
            tmpdir_path = Path(tmpdir)
            try:
                tasks = []
                temp_pages: list[Path] = []
                temp_facts: list[Path] = []
                url_chunks = chunked(urls, parallelism)
                for chunk_idx, url_chunk in enumerate(url_chunks, start=1):
                    url_file = tmpdir_path / f"chunk_{chunk_idx:02d}_urls.txt"
                    url_file.write_text("\n".join(url_chunk) + "\n", encoding="utf-8")
                    part_pages = tmpdir_path / f"part_{chunk_idx:02d}_pages.csv"
                    part_facts = tmpdir_path / f"part_{chunk_idx:02d}_facts.csv"
                    cmd = build_scrape_cmd(args, url_file, part_pages, part_facts)
                    tasks.append((cmd, part_pages, part_facts))
                    temp_pages.append(part_pages)
                    temp_facts.append(part_facts)
                with ThreadPoolExecutor(max_workers=min(parallelism, len(tasks))) as executor:
                    futures = [executor.submit(run_one_scrape, cmd) for cmd, _, _ in tasks]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as exc:
                            print(f"[{idx}/{len(batch_files)}] worker failed: {exc!r}", flush=True)
                            raise
                merge_csvs(temp_pages, pages_csv)
                merge_csvs(temp_facts, facts_csv)
            except Exception:
                print(f"[{idx}/{len(batch_files)}] temp_dir_kept={tmpdir_path}", flush=True)
                raise
            else:
                shutil.rmtree(tmpdir_path, ignore_errors=True)

        if progress_state is not None:
            completed = progress_state.setdefault("completed_batches", [])
            pending = progress_state.setdefault("pending_batches", [])
            if idx not in completed:
                completed.append(idx)
            if idx in pending:
                pending.remove(idx)
            progress_state["last_completed_batch"] = idx
            progress_state["last_completed_batch_file"] = batch_path.name
            if progress_path:
                save_progress(progress_path, progress_state)


if __name__ == "__main__":
    main()
