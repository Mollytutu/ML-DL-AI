import argparse
import csv
import json
from pathlib import Path

from collegedunia_paths import is_review_url


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build ordered school and program URL queues from cleaned seed tables")
    p.add_argument("--school-list-csv", required=True)
    p.add_argument("--program-seeds-csv", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--batch-size", type=int, default=0, help="Optional batch size for chunked txt files")
    p.add_argument(
        "--countries",
        default="",
        help="Optional comma-separated country slugs to keep, e.g. 'usa,canada,uk,australia'.",
    )
    return p.parse_args()


def load_rows(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_txt(path: Path, rows: list[dict], key: str) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            val = row.get(key)
            if val:
                f.write(val + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def chunk_rows(rows: list[dict], batch_size: int) -> list[list[dict]]:
    if batch_size <= 0:
        return [rows]
    return [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]


def write_manifest_and_progress(batch_dir: Path, queue_kind: str, prefix: str, out_dir: Path) -> None:
    batch_files = sorted(batch_dir.glob("*.txt"))
    manifest_path = out_dir / f"{prefix}_manifest.jsonl"
    progress_path = out_dir / f"{prefix}_progress.json"

    manifest_rows = []
    for idx, path in enumerate(batch_files, start=1):
        url_count = sum(1 for _ in path.open("r", encoding="utf-8"))
        manifest_rows.append(
            {
                "batch_index": idx,
                "batch_file": str(path.relative_to(out_dir)),
                "queue_kind": queue_kind,
                "url_count": url_count,
            }
        )

    with manifest_path.open("w", encoding="utf-8") as f:
        for row in manifest_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    progress_state = {
        "queue_kind": queue_kind,
        "total_batches": len(manifest_rows),
        "completed_batches": [],
        "pending_batches": [row["batch_index"] for row in manifest_rows],
    }
    progress_path.write_text(json.dumps(progress_state, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    allowed_countries = {
        item.strip().lower()
        for item in (args.countries or "").split(",")
        if item.strip()
    }

    school_rows = load_rows(args.school_list_csv)
    school_rows = [r for r in school_rows if (r.get("homepage_url") or "").strip() and not is_review_url(r.get("homepage_url"))]
    if allowed_countries:
        school_rows = [r for r in school_rows if (r.get("country") or "").strip().lower() in allowed_countries]
    school_rows.sort(key=lambda r: ((r.get("country") or ""), (r.get("school_name") or ""), (r.get("homepage_url") or "")))
    for r in school_rows:
        r["queue_kind"] = "school_homepage"
        r["queue_url"] = r.get("homepage_url")

    program_rows = load_rows(args.program_seeds_csv)
    program_rows = [r for r in program_rows if (r.get("program_url") or "").strip() and not is_review_url(r.get("program_url"))]
    if allowed_countries:
        program_rows = [r for r in program_rows if (r.get("country") or "").strip().lower() in allowed_countries]
    program_rows.sort(key=lambda r: (
        (r.get("country") or ""),
        (r.get("school_name") or ""),
        (r.get("degree_level") or ""),
        (r.get("program_name") or ""),
        (r.get("program_url") or ""),
    ))
    for r in program_rows:
        r["queue_kind"] = r.get("seed_kind") or "program_detail"
        r["queue_url"] = r.get("program_url")

    school_homepage_rows = [r for r in school_rows if r.get("queue_kind") == "school_homepage"]
    program_detail_rows = [r for r in program_rows if r.get("queue_kind") == "program_detail"]
    program_index_rows = [r for r in program_rows if r.get("queue_kind") == "program_index"]

    school_out_csv = out_dir / "school_queue.csv"
    school_out_txt = out_dir / "school_queue.txt"
    school_out_jsonl = out_dir / "school_queue.jsonl"

    school_homepage_out_csv = out_dir / "school_homepage_queue.csv"
    school_homepage_out_txt = out_dir / "school_homepage_queue.txt"
    school_homepage_out_jsonl = out_dir / "school_homepage_queue.jsonl"

    program_out_csv = out_dir / "program_queue.csv"
    program_out_txt = out_dir / "program_queue.txt"
    program_out_jsonl = out_dir / "program_queue.jsonl"

    program_detail_out_csv = out_dir / "program_detail_queue.csv"
    program_detail_out_txt = out_dir / "program_detail_queue.txt"
    program_detail_out_jsonl = out_dir / "program_detail_queue.jsonl"

    program_index_out_csv = out_dir / "program_index_queue.csv"
    program_index_out_txt = out_dir / "program_index_queue.txt"
    program_index_out_jsonl = out_dir / "program_index_queue.jsonl"

    write_csv(
        school_out_csv,
        school_rows,
        [
            "school_num_id",
            "school_id",
            "country",
            "school_name",
            "homepage_url",
            "seed_kind",
            "source",
            "queue_kind",
            "queue_url",
        ],
    )
    write_txt(school_out_txt, school_rows, "queue_url")
    write_jsonl(school_out_jsonl, school_rows)
    write_csv(
        school_homepage_out_csv,
        school_homepage_rows,
        [
            "school_num_id",
            "school_id",
            "country",
            "school_name",
            "homepage_url",
            "seed_kind",
            "source",
            "queue_kind",
            "queue_url",
        ],
    )
    write_txt(school_homepage_out_txt, school_homepage_rows, "queue_url")
    write_jsonl(school_homepage_out_jsonl, school_homepage_rows)

    write_csv(
        program_out_csv,
        program_rows,
        [
            "program_id",
            "school_id",
            "school_name",
            "country",
            "program_name",
            "degree_level",
            "seed_kind",
            "program_url",
            "source_file",
            "queue_kind",
            "queue_url",
        ],
    )
    write_txt(program_out_txt, program_rows, "queue_url")
    write_jsonl(program_out_jsonl, program_rows)

    write_csv(
        program_detail_out_csv,
        program_detail_rows,
        [
            "program_id",
            "school_id",
            "school_name",
            "country",
            "program_name",
            "degree_level",
            "seed_kind",
            "program_url",
            "source_file",
            "queue_kind",
            "queue_url",
        ],
    )
    write_txt(program_detail_out_txt, program_detail_rows, "queue_url")
    write_jsonl(program_detail_out_jsonl, program_detail_rows)

    write_csv(
        program_index_out_csv,
        program_index_rows,
        [
            "program_id",
            "school_id",
            "school_name",
            "country",
            "program_name",
            "degree_level",
            "seed_kind",
            "program_url",
            "source_file",
            "queue_kind",
            "queue_url",
        ],
    )
    write_txt(program_index_out_txt, program_index_rows, "queue_url")
    write_jsonl(program_index_out_jsonl, program_index_rows)

    if args.batch_size > 0:
        for kind, rows, prefix in [
            ("school", school_rows, "school_queue"),
            ("school_homepage", school_homepage_rows, "school_homepage_queue"),
            ("program", program_rows, "program_queue"),
            ("program_detail", program_detail_rows, "program_detail_queue"),
            ("program_index", program_index_rows, "program_index_queue"),
        ]:
            batches = chunk_rows(rows, args.batch_size)
            batch_dir = out_dir / f"{prefix}_batches"
            batch_dir.mkdir(parents=True, exist_ok=True)
            for idx, batch in enumerate(batches, start=1):
                batch_path = batch_dir / f"{prefix}_{idx:03d}.txt"
                write_txt(batch_path, batch, "queue_url")
            write_manifest_and_progress(batch_dir, kind, prefix, out_dir)

    print(f"school_queue={len(school_rows)}")
    print(f"school_homepage_queue={len(school_homepage_rows)}")
    print(f"program_queue={len(program_rows)}")
    print(f"program_detail_queue={len(program_detail_rows)}")
    print(f"program_index_queue={len(program_index_rows)}")
    print(f"out_dir={out_dir}")


if __name__ == "__main__":
    main()
