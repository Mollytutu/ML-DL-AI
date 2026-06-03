import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export deduplicated school URLs from scraped page CSVs")
    p.add_argument("--pages-csv", required=True)
    p.add_argument("--out-csv", required=True)
    p.add_argument("--out-txt", required=False)
    p.add_argument("--out-jsonl", required=False)
    return p.parse_args()


def load_rows(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    args = parse_args()
    rows = load_rows(args.pages_csv)

    dedup: dict[str, dict] = {}
    for row in rows:
        url = row.get("url")
        if not url:
            continue
        if url not in dedup:
            dedup[url] = {
                "school_num_id": row.get("school_num_id"),
                "school_id": row.get("school_id"),
                "country": row.get("country"),
                "school_name": row.get("school_name_guess") or row.get("title") or row.get("h1"),
                "page_type": row.get("page_type"),
                "status_code": row.get("status_code"),
                "url": url,
            }

    out_rows = list(dedup.values())
    out_rows.sort(key=lambda r: ((r.get("country") or ""), (r.get("school_name") or ""), (r.get("url") or "")))

    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "school_num_id",
                "school_id",
                "country",
                "school_name",
                "page_type",
                "status_code",
                "url",
            ],
        )
        writer.writeheader()
        writer.writerows(out_rows)

    if args.out_txt:
        with open(args.out_txt, "w", encoding="utf-8") as f:
            for row in out_rows:
                f.write((row.get("url") or "") + "\n")

    if args.out_jsonl:
        with open(args.out_jsonl, "w", encoding="utf-8") as f:
            for row in out_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"urls={len(out_rows)}")
    print(f"out_csv={args.out_csv}")
    if args.out_txt:
        print(f"out_txt={args.out_txt}")
    if args.out_jsonl:
        print(f"out_jsonl={args.out_jsonl}")


if __name__ == "__main__":
    main()
