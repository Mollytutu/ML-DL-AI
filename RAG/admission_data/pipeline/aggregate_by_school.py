import argparse
import csv
import json
import re
from collections import Counter, defaultdict

from collegedunia_paths import is_review_url, page_role_from_url
from csv_safety import clean_local_currency_text, sanitize_row

SIGNAL_FIELDS = [
    "has_deadline_signal",
    "has_exam_signal",
    "has_acceptance_signal",
    "has_applications_signal",
    "has_admitted_signal",
    "has_enrolled_signal",
    "has_yield_signal",
]

KNOWN_ACRONYMS = {"uk", "usa", "uae", "ucla", "mit", "uc", "nyu", "ntu", "nus", "kcl", "lse", "lmu"}
COUNTRY_CODE_OVERRIDES = {
    "australia": "AU",
    "canada": "CA",
    "india": "IN",
    "new zealand": "NZ",
    "singapore": "SG",
    "uae": "AE",
    "uk": "UK",
    "united kingdom": "UK",
    "usa": "US",
    "united states": "US",
    "united states of america": "US",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Aggregate Collegedunia page/fact CSVs by school_id")
    p.add_argument("--pages-csv", required=True)
    p.add_argument("--facts-csv", required=True)
    p.add_argument("--summary-csv", required=True)
    p.add_argument("--school-facts-csv", required=True)
    p.add_argument("--admission-summary-csv")
    p.add_argument("--admission-facts-csv")
    p.add_argument("--min-pages-per-school", type=int, default=1)
    return p.parse_args()


def load_rows(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def pick_mode(values: list[str | None]) -> str | None:
    cleaned = [v for v in values if v not in {None, ""}]
    if not cleaned:
        return None
    return Counter(cleaned).most_common(1)[0][0]


def display_name_from_school_id(school_id: str) -> str:
    parts = school_id.split("_")
    if parts and parts[0] == "unknown":
        parts = parts[1:]
    elif parts:
        parts = parts[1:]

    words = []
    for part in parts:
        if part in KNOWN_ACRONYMS:
            words.append(part.upper())
        else:
            words.append(part.capitalize())
    return " ".join(words).strip() or school_id


def country_code_from_country(country: str | None) -> str:
    raw = (country or "unknown").strip().lower()
    if raw in COUNTRY_CODE_OVERRIDES:
        return COUNTRY_CODE_OVERRIDES[raw]
    letters = re.sub(r"[^a-z]+", "", raw)
    if not letters:
        return "UN"
    if len(letters) >= 2:
        return letters[:2].upper()
    return (letters.upper() + "X")[:2]


def school_name_sort_key(row: dict) -> tuple[str, str]:
    candidate = (
        row.get("school_name_guess")
        or row.get("program_name_guess")
        or row.get("h1")
        or row.get("title")
        or ""
    )
    candidate = re.sub(r"\s+", " ", candidate).strip().lower()
    return candidate, row.get("school_id") or ""


def cleaned_school_name(row: dict) -> str | None:
    candidates = [
        row.get("school_name_guess"),
        row.get("program_name_guess"),
        row.get("h1"),
        row.get("title"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        text = re.sub(r"\s+", " ", candidate).strip()
        text = text.split(":", 1)[0].strip()
        text = re.sub(
            r"\s*-\s*(admissions?|fees?|rankings?|scholarships?|courses?|programs?).*$",
            "",
            text,
            flags=re.I,
        ).strip()
        text = re.sub(
            r"\s+(reviews? and ratings?|reviews?|ratings?|gallery|scholarships?|courses?|fees?|rankings?|admission alerts?|admission)$",
            "",
            text,
            flags=re.I,
        ).strip()
        if text:
            return text
    return None


def infer_school_id(row: dict) -> str:
    existing = (row.get("school_id") or "").strip()
    if existing and existing != "unknown":
        return existing

    country = slugify_value(row.get("country") or "unknown")
    name = cleaned_school_name(row)
    if not name:
        name = row.get("school_name_guess") or row.get("program_name_guess") or row.get("h1") or row.get("title") or ""
    name = re.sub(r"\s+", " ", name).strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    if not name:
        url = row.get("url") or ""
        tail = url.rsplit("/", 1)[-1] if url else ""
        tail = re.sub(r"^\d+-", "", tail)
        tail = re.sub(r"[^a-z0-9]+", "_", tail.lower()).strip("_")
        name = tail or "unknown"
    return f"{country}_{name}"


def slugify_value(value: str | None) -> str:
    text = (value or "unknown").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unknown"


def normalize_role(row: dict) -> str:
    url = row.get("source_url") or row.get("url") or ""
    page_type = (row.get("page_type") or "").strip().lower()
    if page_type == "school_review":
        return "school_homepage"
    if is_review_url(url):
        return "other"
    role = page_role_from_url(url)
    if role == "other" and page_type in {"university", "college", "institute", "school", "admission"}:
        role = "school_homepage"
    return role


def main() -> None:
    args = parse_args()
    page_rows = load_rows(args.pages_csv)
    fact_rows = load_rows(args.facts_csv)

    pages_by_school: dict[str, list[dict]] = defaultdict(list)
    facts_by_school: dict[str, list[dict]] = defaultdict(list)
    admission_pages_by_school: dict[str, list[dict]] = defaultdict(list)
    admission_facts_by_school: dict[str, list[dict]] = defaultdict(list)

    for row in page_rows:
        school_id = infer_school_id(row)
        row["school_id"] = school_id
        row["page_role"] = normalize_role(row)
        if row["page_role"] == "school_homepage":
            pages_by_school[school_id].append(row)
        elif row["page_role"] == "admission":
            admission_pages_by_school[school_id].append(row)
        elif row["page_role"] == "other":
            continue

    for row in fact_rows:
        school_id = infer_school_id(row)
        row["school_id"] = school_id
        row["page_role"] = normalize_role(row)
        if row["page_role"] == "school_homepage":
            cleaned_fact_value = clean_local_currency_text(row.get("fact_value"))
            if not cleaned_fact_value:
                continue
            row["fact_value"] = cleaned_fact_value
            facts_by_school[school_id].append(row)
        elif row["page_role"] == "admission":
            cleaned_fact_value = clean_local_currency_text(row.get("fact_value"))
            if not cleaned_fact_value:
                continue
            row["fact_value"] = cleaned_fact_value
            admission_facts_by_school[school_id].append(row)
        else:
            continue

    summary_rows: list[dict] = []
    school_fact_rows: list[dict] = []
    admission_summary_rows: list[dict] = []
    admission_fact_rows: list[dict] = []

    for school_id, rows in pages_by_school.items():
        if len(rows) < args.min_pages_per_school:
            continue

        fact_rows_for_school = facts_by_school.get(school_id, [])
        countries = [r.get("country") for r in rows]
        page_types = [r.get("page_type") for r in rows]
        school_names = [r.get("school_name_guess") for r in rows]
        program_names = [r.get("program_name_guess") for r in rows]

        signal_counts = {field: 0 for field in SIGNAL_FIELDS}
        for row in rows:
            for field in SIGNAL_FIELDS:
                if row.get(field) == "yes":
                    signal_counts[field] += 1

        unique_urls = sorted({r.get("url") for r in rows if r.get("url")})
        unique_facts = {}
        for row in fact_rows_for_school:
            key = (row.get("fact_key") or "", row.get("fact_value") or "")
            if key[0] and key[1]:
                unique_facts.setdefault(key, row)

        summary_rows.append(
            {
                "school_id": school_id,
                "country": pick_mode(countries),
                "school_name_guess": cleaned_school_name(rows[0]) or pick_mode(school_names) or display_name_from_school_id(school_id),
                "program_name_guess": pick_mode(program_names),
                "page_count": len(rows),
                "fact_count": len(fact_rows_for_school),
                "unique_fact_count": len(unique_facts),
                "unique_url_count": len(unique_urls),
                "page_types": "|".join(sorted({p for p in page_types if p})),
                **{field: signal_counts[field] for field in SIGNAL_FIELDS},
            }
        )

        for (fact_key, fact_value), source_row in unique_facts.items():
            school_fact_rows.append(
                {
                    "school_id": school_id,
                    "country": source_row.get("country"),
                    "school_name_guess": source_row.get("school_name_guess"),
                    "program_name_guess": source_row.get("program_name_guess"),
                    "fact_key": fact_key,
                    "fact_value": fact_value,
                    "source_url": source_row.get("url"),
                    "page_type": source_row.get("page_type"),
                    "crawl_depth": source_row.get("crawl_depth"),
                    "parent_url": source_row.get("parent_url"),
                    "scraped_at": source_row.get("scraped_at"),
                }
            )

    for school_id, rows in admission_pages_by_school.items():
        if len(rows) < args.min_pages_per_school:
            continue

        facts = admission_facts_by_school.get(school_id, [])
        countries = [r.get("country") for r in rows]
        page_types = [r.get("page_type") for r in rows]
        school_names = [r.get("school_name_guess") for r in rows]
        unique_urls = sorted({r.get("url") for r in rows if r.get("url")})
        unique_facts = {}
        for row in facts:
            key = (row.get("fact_key") or "", row.get("fact_value") or "")
            if key[0] and key[1]:
                unique_facts.setdefault(key, row)

        admission_summary_rows.append(
            {
                "school_id": school_id,
                "country": pick_mode(countries),
                "school_name_guess": cleaned_school_name(rows[0]) or pick_mode(school_names) or display_name_from_school_id(school_id),
                "admission_url": rows[0].get("url"),
                "page_count": len(rows),
                "fact_count": len(facts),
                "unique_fact_count": len(unique_facts),
                "unique_url_count": len(unique_urls),
                "page_types": "|".join(sorted({p for p in page_types if p})),
            }
        )

        for (fact_key, fact_value), source_row in unique_facts.items():
            admission_fact_rows.append(
                {
                    "school_id": school_id,
                    "country": source_row.get("country"),
                    "school_name_guess": source_row.get("school_name_guess"),
                    "admission_url": rows[0].get("url"),
                    "fact_key": fact_key,
                    "fact_value": fact_value,
                    "source_url": source_row.get("url"),
                    "page_role": source_row.get("page_role"),
                    "page_type": source_row.get("page_type"),
                    "crawl_depth": source_row.get("crawl_depth"),
                    "parent_url": source_row.get("parent_url"),
                    "scraped_at": source_row.get("scraped_at"),
                }
            )

    num_id_by_school: dict[str, str] = {}
    country_groups: dict[str, list[dict]] = defaultdict(list)
    for row in summary_rows:
        country_groups[country_code_from_country(row.get("country"))].append(row)

    for country_code, rows in sorted(country_groups.items()):
        for idx, row in enumerate(sorted(rows, key=school_name_sort_key), start=1):
            num_id_by_school[row["school_id"]] = f"{country_code}{idx:05d}"

    for row in summary_rows:
        row["school_num_id"] = num_id_by_school.get(row["school_id"])

    for row in school_fact_rows:
        row["school_num_id"] = num_id_by_school.get(row["school_id"])
    for row in admission_summary_rows:
        row["school_num_id"] = num_id_by_school.get(row["school_id"])
    for row in admission_fact_rows:
        row["school_num_id"] = num_id_by_school.get(row["school_id"])

    with open(args.summary_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "school_id",
                "school_num_id",
                "country",
                "school_name_guess",
                "program_name_guess",
                "page_count",
                "fact_count",
                "unique_fact_count",
                "unique_url_count",
                "page_types",
                *SIGNAL_FIELDS,
            ],
        )
        writer.writeheader()
        writer.writerows(
            sanitize_row(
                row,
                [
                    "school_id",
                    "school_num_id",
                    "country",
                    "school_name_guess",
                    "program_name_guess",
                    "page_count",
                    "fact_count",
                    "unique_fact_count",
                    "unique_url_count",
                    "page_types",
                    *SIGNAL_FIELDS,
                ],
            )
            for row in summary_rows
        )

    summary_jsonl = args.summary_csv.rsplit(".", 1)[0] + ".jsonl" if "." in args.summary_csv else args.summary_csv + ".jsonl"
    with open(summary_jsonl, "w", encoding="utf-8") as f:
        for row in summary_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with open(args.school_facts_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "school_id",
                "school_num_id",
                "country",
                "school_name_guess",
                "program_name_guess",
                "fact_key",
                "fact_value",
                "source_url",
                "page_type",
                "crawl_depth",
                "parent_url",
                "scraped_at",
            ],
        )
        writer.writeheader()
        writer.writerows(
            sanitize_row(
                row,
                [
                    "school_id",
                    "school_num_id",
                    "country",
                    "school_name_guess",
                    "program_name_guess",
                    "fact_key",
                    "fact_value",
                    "source_url",
                    "page_type",
                    "crawl_depth",
                    "parent_url",
                    "scraped_at",
                ],
            )
            for row in school_fact_rows
        )

    if args.admission_summary_csv:
        with open(args.admission_summary_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "school_id",
                    "school_num_id",
                    "country",
                    "school_name_guess",
                    "admission_url",
                    "page_count",
                    "fact_count",
                    "unique_fact_count",
                    "unique_url_count",
                    "page_types",
                ],
            )
            writer.writeheader()
            writer.writerows(sanitize_row(row, writer.fieldnames) for row in admission_summary_rows)
    if args.admission_facts_csv:
        with open(args.admission_facts_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "school_id",
                    "school_num_id",
                    "country",
                    "school_name_guess",
                    "admission_url",
                    "fact_key",
                    "fact_value",
                    "source_url",
                    "page_role",
                    "page_type",
                    "crawl_depth",
                    "parent_url",
                    "scraped_at",
                ],
            )
            writer.writeheader()
            writer.writerows(sanitize_row(row, writer.fieldnames) for row in admission_fact_rows)

    print(f"schools={len(summary_rows)}")
    print(f"school_facts={len(school_fact_rows)}")
    print(f"summary_csv={args.summary_csv}")
    print(f"summary_jsonl={summary_jsonl}")
    print(f"school_facts_csv={args.school_facts_csv}")


if __name__ == "__main__":
    main()
