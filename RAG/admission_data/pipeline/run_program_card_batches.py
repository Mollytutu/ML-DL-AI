import argparse
import csv
import subprocess
import sys
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run extract_program_cards.py over URL batches in parallel and merge outputs.")
    p.add_argument("--urls-file", required=True)
    p.add_argument("--workspace-root", required=True)
    p.add_argument("--batch-size", type=int, default=25)
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--wait-sec", type=float, default=6.0)
    headless_group = p.add_mutually_exclusive_group()
    headless_group.add_argument("--headless", dest="headless", action="store_true")
    headless_group.add_argument("--no-headless", dest="headless", action="store_false")
    p.set_defaults(headless=True)
    return p.parse_args()


def load_urls(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def chunked(items: list[str], batch_size: int) -> list[list[str]]:
    if batch_size <= 0:
        return [items]
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def write_urls(path: Path, urls: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(urls) + "\n", encoding="utf-8")


def merge_csv(inputs: list[Path], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    rows_written = 0
    out_handle = None
    try:
        for path in inputs:
            with path.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if not fieldnames:
                    fieldnames = reader.fieldnames or []
                    out_handle = output.open("w", newline="", encoding="utf-8")
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
    return rows_written


def run_batch(batch_idx: int, batch_urls: list[str], workspace_root: Path, wait_sec: float, headless: bool) -> tuple[Path, Path]:
    batch_dir = workspace_root / "batches" / f"batch_{batch_idx:03d}"
    urls_file = batch_dir / "urls.txt"
    output_csv = batch_dir / "programs.csv"
    summary_csv = batch_dir / "summary.csv"
    write_urls(urls_file, batch_urls)

    cmd = [
        sys.executable,
        "pipeline/extract_program_cards.py",
        "--urls-file",
        str(urls_file),
        "--output-csv",
        str(output_csv),
        "--summary-csv",
        str(summary_csv),
        "--wait-sec",
        str(wait_sec),
    ]
    cmd.append("--headless" if headless else "--no-headless")
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)
    return output_csv, summary_csv


def main() -> None:
    args = parse_args()
    workspace_root = Path(args.workspace_root)
    urls = load_urls(Path(args.urls_file))
    batches = chunked(urls, args.batch_size)
    if not batches:
        raise SystemExit("no URLs to process")

    program_csvs: list[Path] = []
    summary_csvs: list[Path] = []
    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
        futures = {
            executor.submit(run_batch, idx, batch_urls, workspace_root, args.wait_sec, args.headless): idx
            for idx, batch_urls in enumerate(batches, start=1)
        }
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                idx = futures.pop(future)
                output_csv, summary_csv = future.result()
                program_csvs.append(output_csv)
                summary_csvs.append(summary_csv)
                print(f"completed_batch={idx}")

    merged_programs = workspace_root / "programs.csv"
    merged_summary = workspace_root / "program_summary.csv"
    program_rows = merge_csv(sorted(program_csvs), merged_programs)
    summary_rows = merge_csv(sorted(summary_csvs), merged_summary)
    print(f"merged_program_rows={program_rows}")
    print(f"merged_summary_rows={summary_rows}")
    print(f"programs_csv={merged_programs}")
    print(f"summary_csv={merged_summary}")


if __name__ == "__main__":
    main()
