import argparse
import csv
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COUNTRY_LABELS = {
    "usa": "USA",
    "uk": "UK",
    "uae": "UAE",
    "hong-kong": "Hong Kong",
    "new-zealand": "New Zealand",
}


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else PROJECT_ROOT / path


def format_country_label(country: str) -> str:
    normalized = (country or "").strip()
    if not normalized:
        return "Unknown"
    return COUNTRY_LABELS.get(normalized, normalized.replace("-", " ").title())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a country-level school and program list")
    parser.add_argument("--school-list-csv", default="data/raw/pipeline_inputs/school_list.csv")
    parser.add_argument("--program-seeds-csv", default="data/raw/pipeline_inputs/collegedunia_program_seeds_from_raw.csv")
    parser.add_argument("--out-csv", default="data/run/reports/country_school_summary.csv")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    school_list_csv = resolve_path(args.school_list_csv)
    program_seeds_csv = resolve_path(args.program_seeds_csv)
    out_csv = resolve_path(args.out_csv)

    with school_list_csv.open(newline="", encoding="utf-8") as handle:
        school_rows = list(csv.DictReader(handle))

    with program_seeds_csv.open(newline="", encoding="utf-8") as handle:
        program_rows = list(csv.DictReader(handle))

    school_counts = Counter((row.get("country") or "unknown").strip() or "unknown" for row in school_rows)
    program_counts = Counter((row.get("country") or "unknown").strip() or "unknown" for row in program_rows)
    countries = sorted(set(school_counts) | set(program_counts), key=lambda item: (-school_counts[item], item))
    summary_rows = [
        {
            "country": country,
            "school_count": school_counts.get(country, 0),
            "program_count": program_counts.get(country, 0),
            "summary": f"{format_country_label(country)} {school_counts.get(country, 0)} school, {program_counts.get(country, 0)} program",
        }
        for country in countries
    ]

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["country", "school_count", "program_count", "summary"])
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"countries={len(summary_rows)}")
    print(f"schools={len(school_rows)}")
    print(f"programs={len(program_rows)}")
    print(f"out_csv={out_csv}")


if __name__ == "__main__":
    main()
