import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from collegedunia_paths import is_review_url
from csv_safety import clean_local_currency_text, sanitize_row

URL_RE = re.compile(r"https?://[^/]+/([^/]+)/([^/]+)/(\d+)-(.+)$")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge and dedupe school-page outputs into one reviewed file."
    )
    parser.add_argument(
        "--facts-dir",
        default="data/clean/school_pages",
        help="Directory containing per-run school-page CSV files.",
    )
    parser.add_argument(
        "--facts-dirs",
        nargs="*",
        default=[],
        help="Additional directories containing per-run school-page CSV files.",
    )
    parser.add_argument(
        "--clean-lists",
        nargs="*",
        default=[
            "data/raw/pipeline_inputs/school_list.csv",
            "data/raw/pipeline_inputs/collegedunia_school_seeds_from_raw.csv",
        ],
        help="Preferred school lists used to choose homepage URLs and names, with the reviewed school list first.",
    )
    parser.add_argument(
        "--out-csv",
        default="data/clean/school_pages/school_pages.csv",
        help="Merged CSV output path.",
    )
    parser.add_argument(
        "--out-jsonl",
        default="data/clean/school_pages/school_pages.jsonl",
        help="Merged JSONL output path.",
    )
    parser.add_argument(
        "--out-summary",
        default="data/clean/school_pages/school_pages_summary.json",
        help="Summary JSON output path.",
    )
    return parser.parse_args()


def resolve_path(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else PROJECT_ROOT / path


def parse_school_url(url: str) -> dict | None:
    match = URL_RE.search((url or "").strip())
    if not match:
        return None
    country, kind, numeric_id, slug = match.groups()
    return {
        "country": country,
        "kind": kind,
        "numeric_id": numeric_id,
        "slug": slug,
        "institution_key": f"{country}:{numeric_id}",
    }


def load_clean_lookup(paths: list[str]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for priority, path_str in enumerate(paths):
        path = Path(path_str)
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                parsed = parse_school_url(row.get("homepage_url", ""))
                if not parsed:
                    continue
                key = parsed["institution_key"]
                candidate = {
                    "priority": priority,
                    "homepage_url": row.get("homepage_url", ""),
                    "school_id": row.get("school_id", ""),
                    "school_num_id": row.get("school_num_id", ""),
                    "school_name": row.get("school_name", ""),
                    "kind": parsed["kind"],
                }
                existing = lookup.get(key)
                if existing is None or score_clean_candidate(candidate) < score_clean_candidate(existing):
                    lookup[key] = candidate
    return lookup


def score_clean_candidate(candidate: dict) -> tuple:
    return (
        candidate.get("priority", 999),
        0 if candidate.get("kind") == "university" else 1,
        len(candidate.get("homepage_url", "")),
        candidate.get("homepage_url", ""),
    )


def normalize_row(row: dict, source_file: str) -> dict:
    source_url = row.get("source_url") or row.get("url") or ""
    parsed = parse_school_url(source_url)
    normalized = {
        "source_file": source_file,
        "source_url": source_url,
        "school_id": row.get("school_id", "").strip(),
        "school_num_id": row.get("school_num_id", "").strip(),
        "country": row.get("country", "").strip(),
        "school_name_guess": row.get("school_name_guess", "").strip(),
        "program_name_guess": row.get("program_name_guess", "").strip(),
        "fact_key": row.get("fact_key", "").strip(),
        "fact_value": row.get("fact_value", "").strip(),
        "page_type": row.get("page_type", "").strip(),
        "crawl_depth": row.get("crawl_depth", "").strip(),
        "parent_url": row.get("parent_url", "").strip(),
        "scraped_at": row.get("scraped_at", "").strip(),
        "institution_key": parsed["institution_key"] if parsed else "",
        "institution_country": parsed["country"] if parsed else "",
        "institution_kind": parsed["kind"] if parsed else "",
        "institution_numeric_id": parsed["numeric_id"] if parsed else "",
        "institution_slug": parsed["slug"] if parsed else "",
    }
    return normalized


def is_school_homepage_fact(row: dict) -> bool:
    page_type = (row.get("page_type") or "").strip().lower()
    if page_type not in {"university", "college", "institute", "school", "school_review"}:
        return False
    if page_type == "school_review":
        return True
    source_url = row.get("source_url") or row.get("url") or ""
    return not is_review_url(source_url)


def choose_preferred_url(urls: list[str], clean_entry: dict | None) -> str:
    if clean_entry and clean_entry.get("homepage_url"):
        return clean_entry["homepage_url"]
    counts = Counter(urls)
    ranked = sorted(
        counts.items(),
        key=lambda item: (
            -item[1],
            0 if (parse_school_url(item[0]) or {}).get("kind") == "university" else 1,
            len(item[0]),
            item[0],
        ),
    )
    return ranked[0][0] if ranked else ""


def choose_preferred_value(values: list[str], fallback: str = "") -> str:
    values = [value for value in values if value]
    if not values:
        return fallback
    counts = Counter(values)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    return ranked[0][0]


def merge_group(rows: list[dict], clean_entry: dict | None) -> dict:
    urls = [row["source_url"] for row in rows if row["source_url"]]
    chosen_url = choose_preferred_url(urls, clean_entry)
    parsed_url = parse_school_url(chosen_url) or parse_school_url(rows[0]["source_url"])
    school_id = clean_entry.get("school_id", "") if clean_entry else ""
    if not school_id:
        school_id = choose_preferred_value(
            [row["school_id"] for row in rows if not row["school_id"].startswith("unknown_")]
        )
    school_num_id = clean_entry.get("school_num_id", "") if clean_entry else ""
    if not school_num_id:
        school_num_id = choose_preferred_value([row["school_num_id"] for row in rows])
    school_name = clean_entry.get("school_name", "") if clean_entry else ""
    if not school_name:
        school_name = choose_preferred_value([row["school_name_guess"] for row in rows])
    scraped_times = sorted({row["scraped_at"] for row in rows if row["scraped_at"]})
    page_type = choose_preferred_value([row["page_type"] for row in rows])
    return {
        "institution_key": rows[0]["institution_key"],
        "country": (parsed_url or {}).get("country", rows[0]["country"]),
        "institution_numeric_id": (parsed_url or {}).get("numeric_id", rows[0]["institution_numeric_id"]),
        "institution_slug": (parsed_url or {}).get("slug", rows[0]["institution_slug"]),
        "school_id": school_id,
        "school_num_id": school_num_id,
        "school_name_guess": school_name,
        "fact_key": rows[0]["fact_key"],
        "fact_value": rows[0]["fact_value"],
        "source_url": chosen_url,
        "page_type": page_type,
        "source_file_count": len({row["source_file"] for row in rows}),
        "duplicate_count": len(rows),
        "source_files": "|".join(sorted({row["source_file"] for row in rows})),
        "school_ids_observed": "|".join(sorted({row["school_id"] for row in rows if row["school_id"]})),
        "school_num_ids_observed": "|".join(sorted({row["school_num_id"] for row in rows if row["school_num_id"]})),
        "source_urls_observed": "|".join(sorted({row["source_url"] for row in rows if row["source_url"]})),
        "page_types_observed": "|".join(sorted({row["page_type"] for row in rows if row["page_type"]})),
        "first_scraped_at": scraped_times[0] if scraped_times else "",
        "last_scraped_at": scraped_times[-1] if scraped_times else "",
    }


def main() -> None:
    args = parse_args()
    facts_dirs = [resolve_path(args.facts_dir), *[resolve_path(path) for path in args.facts_dirs]]
    out_csv = resolve_path(args.out_csv)
    out_jsonl = resolve_path(args.out_jsonl)
    out_summary = resolve_path(args.out_summary)

    clean_lookup = load_clean_lookup([str(resolve_path(path)) for path in args.clean_lists])
    rows_by_key: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    source_files: list[Path] = []

    stats = {
        "source_files": [],
        "input_rows": 0,
        "dropped_unknown_rows": 0,
        "dropped_unparseable_rows": 0,
        "dropped_non_homepage_rows": 0,
        "dropped_currency_rows": 0,
    }

    for facts_dir in facts_dirs:
        if not facts_dir.exists():
            continue
        for path in sorted(
            facts_dir.glob("*school_facts.csv"),
        ):
            if "merged_dedup" in path.name:
                continue
            source_files.append(path)

    source_files = sorted({path.resolve() for path in source_files}, key=lambda path: str(path))
    stats["source_files"] = [path.name for path in source_files]

    for path in source_files:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for raw_row in reader:
                stats["input_rows"] += 1
                row = normalize_row(raw_row, path.name)
                if row["school_id"].startswith("unknown_"):
                    stats["dropped_unknown_rows"] += 1
                    continue
                if not row["institution_key"]:
                    stats["dropped_unparseable_rows"] += 1
                    continue
                if not is_school_homepage_fact(row):
                    stats["dropped_non_homepage_rows"] += 1
                    continue
                row["fact_value"] = clean_local_currency_text(row.get("fact_value"))
                if not row["fact_value"]:
                    stats["dropped_currency_rows"] += 1
                    continue
                dedupe_key = (row["institution_key"], row["fact_key"], row["fact_value"])
                rows_by_key[dedupe_key].append(row)

    merged_rows = []
    for key in sorted(rows_by_key):
        institution_key = key[0]
        merged_rows.append(merge_group(rows_by_key[key], clean_lookup.get(institution_key)))

    fieldnames = [
        "institution_key",
        "country",
        "institution_numeric_id",
        "institution_slug",
        "school_id",
        "school_num_id",
        "school_name_guess",
        "fact_key",
        "fact_value",
        "source_url",
        "page_type",
        "source_file_count",
        "duplicate_count",
        "source_files",
        "school_ids_observed",
        "school_num_ids_observed",
        "source_urls_observed",
        "page_types_observed",
        "first_scraped_at",
        "last_scraped_at",
    ]

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sanitize_row(row, fieldnames) for row in merged_rows)

    with out_jsonl.open("w", encoding="utf-8") as handle:
        for row in merged_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    stats.update(
        {
            "kept_rows": len(merged_rows),
            "removed_duplicate_rows": stats["input_rows"]
            - stats["dropped_unknown_rows"]
            - stats["dropped_unparseable_rows"]
            - stats["dropped_non_homepage_rows"]
            - stats["dropped_currency_rows"]
            - len(merged_rows),
            "unique_institutions": len({row["institution_key"] for row in merged_rows}),
            "institutions_with_clean_list_match": len(
                {row["institution_key"] for row in merged_rows if row["institution_key"] in clean_lookup}
            ),
            "institutions_without_clean_list_match": len(
                {row["institution_key"] for row in merged_rows if row["institution_key"] not in clean_lookup}
            ),
            "out_csv": str(out_csv),
            "out_jsonl": str(out_jsonl),
        }
    )
    out_summary.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
