import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Split school list CSV into per-country files")
    p.add_argument("--school-list-csv", required=True)
    p.add_argument("--out-dir", required=True)
    return p.parse_args()


def slug_country(value: str | None) -> str:
    if not value:
        return "unknown"
    text = value.strip().lower()
    text = "".join(ch if ch.isalnum() else "_" for ch in text)
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_") or "unknown"


def main() -> None:
    args = parse_args()
    input_path = Path(args.school_list_csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    buckets: dict[str, list[dict]] = {}
    for row in rows:
        country = slug_country(row.get("country"))
        buckets.setdefault(country, []).append(row)

    for country, country_rows in buckets.items():
        out_path = out_dir / f"school_list_{country}.csv"
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(country_rows)

    print(f"countries={len(buckets)}")
    print(f"schools={len(rows)}")
    print(f"out_dir={out_dir}")


if __name__ == "__main__":
    main()
