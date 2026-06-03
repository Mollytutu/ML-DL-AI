import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from collegedunia_paths import (
    country_code_from_value,
    country_from_url,
    infer_degree_level,
    infer_program_id,
    infer_program_name_from_row,
    infer_school_id_from_row,
    infer_school_name_from_row,
    is_review_url,
    normalize_program_level,
    page_role_from_url,
    school_homepage_from_url,
    slugify,
)
from csv_safety import clean_local_currency_text


SIGNAL_FIELDS = [
    "has_deadline_signal",
    "has_exam_signal",
    "has_acceptance_signal",
    "has_applications_signal",
    "has_admitted_signal",
    "has_enrolled_signal",
    "has_yield_signal",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Split Collegedunia scraped rows into school and program tables")
    p.add_argument("--pages-csv", required=True)
    p.add_argument("--facts-csv", required=True)
    p.add_argument("--school-summary-csv", required=True)
    p.add_argument("--school-facts-csv", required=True)
    p.add_argument("--program-summary-csv", required=True)
    p.add_argument("--program-facts-csv", required=True)
    p.add_argument("--school-summary-jsonl")
    p.add_argument("--admission-summary-csv")
    p.add_argument("--admission-facts-csv")
    p.add_argument("--admission-summary-jsonl")
    p.add_argument("--program-summary-jsonl")
    p.add_argument("--min-school-pages", type=int, default=1)
    p.add_argument("--min-program-pages", type=int, default=1)
    return p.parse_args()


def load_rows(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def normalize_role(row: dict) -> str:
    url = row.get("url") or ""
    if is_review_url(url):
        return "other"
    role = page_role_from_url(url)
    page_type = (row.get("page_type") or "").strip().lower()
    if role == "other" and not is_review_url(url):
        if page_type == "program":
            role = "program"
        elif page_type in {"university", "college", "institute", "school", "admission"}:
            role = "school_homepage"
    return role


def cleaned_name(row: dict, fallback_url: str | None = None) -> str | None:
    return infer_school_name_from_row(row, fallback_url=fallback_url)


def pick_mode(values: list[str | None]) -> str | None:
    cleaned = [v for v in values if v not in {None, ""}]
    if not cleaned:
        return None
    return Counter(cleaned).most_common(1)[0][0]


def school_sort_key(row: dict) -> tuple[str, str]:
    candidate = (row.get("school_name") or row.get("school_name_guess") or row.get("school_id") or "")
    return slugify(candidate), row.get("school_id") or ""


def program_sort_key(row: dict) -> tuple[str, str, str]:
    return (
        slugify(row.get("school_name") or row.get("school_name_guess") or row.get("school_id") or ""),
        slugify(row.get("program_name") or row.get("program_name_guess") or row.get("program_id") or ""),
        row.get("program_id") or "",
    )


def program_name_from_fact_value(fact_value: str | None) -> str | None:
    text = clean_local_currency_text(fact_value) or (fact_value or "")
    text = text.split(":", 1)[0].strip()
    text = re.sub(r"^\(\s*\d+\s+Views?(?:\s+Last Year)?\s*\)\s*", "", text, flags=re.I).strip()
    text = re.sub(r"\s*\(\d+\s+Views?.*?\)\s*$", "", text, flags=re.I).strip()
    text = re.sub(r"\s*\(\d+\s+views?.*?\)\s*$", "", text, flags=re.I).strip()
    text = re.sub(r"\s*-\s*(fees?|eligibility|deadline|admission).*$", "", text, flags=re.I).strip()
    if re.match(
        r"^(application deadline|students? admitted|1 on 1 interaction|content curator|updated|download|apply now|view all courses|course details|admission deadline)",
        text,
        flags=re.I,
    ):
        return None
    if text:
        return text
    return None


def build_school_tables(page_rows: list[dict], fact_rows: list[dict], min_school_pages: int):
    school_page_rows: list[dict] = []
    school_page_url_to_id: dict[str, str] = {}
    school_homepage_url_by_school_id: dict[str, str] = {}

    # First pass: lock homepage IDs so subpages can inherit them.
    for row in page_rows:
        row["page_role"] = normalize_role(row)
        url = row.get("url") or ""
        role = row["page_role"]
        if role != "school_homepage":
            continue
        school_id = infer_school_id_from_row(row)
        row["school_id"] = school_id
        school_page_rows.append(row)
        if url:
            school_page_url_to_id[url] = school_id
            school_homepage_url_by_school_id.setdefault(school_id, school_homepage_from_url(url) or url)
        home = school_homepage_from_url(url)
        if home:
            school_page_url_to_id[home] = school_id
            school_homepage_url_by_school_id.setdefault(school_id, home)

    # Second pass: attach subpages to the nearest known school homepage.
    for row in page_rows:
        if row.get("page_role") != "school_subpage":
            continue
        url = row.get("url") or ""
        parent_url = row.get("parent_url") or ""
        school_id = (
            school_page_url_to_id.get(parent_url)
            or school_page_url_to_id.get(school_homepage_from_url(url) or "")
            or school_page_url_to_id.get(school_homepage_from_url(parent_url) or "")
            or infer_school_id_from_row(row, fallback_url=parent_url or url)
        )
        row["school_id"] = school_id
        school_page_rows.append(row)
        if url:
            school_page_url_to_id[url] = school_id
            school_homepage_url_by_school_id.setdefault(school_id, school_homepage_from_url(url) or parent_url or url)

    school_pages_by_id: dict[str, list[dict]] = defaultdict(list)
    for row in school_page_rows:
        school_pages_by_id[row["school_id"]].append(row)

    school_facts_by_id: dict[str, list[dict]] = defaultdict(list)
    for row in fact_rows:
        role = normalize_role(row)
        url = row.get("url") or ""
        if role != "school_homepage":
            continue
        cleaned_fact_value = clean_local_currency_text(row.get("fact_value"))
        if not cleaned_fact_value:
            continue
        school_id = (
            row.get("school_id")
            or school_page_url_to_id.get(row.get("parent_url") or "")
            or school_page_url_to_id.get(url)
            or infer_school_id_from_row(row, fallback_url=row.get("parent_url") or url)
        )
        row["school_id"] = school_id
        row["fact_value"] = cleaned_fact_value
        school_facts_by_id[school_id].append(row)

    summary_rows: list[dict] = []
    school_fact_rows: list[dict] = []

    for school_id, rows in school_pages_by_id.items():
        if len(rows) < min_school_pages:
            continue

        facts = school_facts_by_id.get(school_id, [])
        countries = [r.get("country") for r in rows if r.get("country")]
        page_types = [r.get("page_type") for r in rows if r.get("page_type")]
        page_roles = [r.get("page_role") for r in rows if r.get("page_role")]
        school_names = [cleaned_name(r, fallback_url=r.get("url")) for r in rows]
        signal_counts = {field: 0 for field in SIGNAL_FIELDS}
        for row in rows:
            for field in SIGNAL_FIELDS:
                if row.get(field) in {"1", "yes", "true", True}:
                    signal_counts[field] += 1

        unique_urls = sorted({r.get("url") for r in rows if r.get("url")})
        unique_facts: dict[tuple[str, str], dict] = {}
        for row in facts:
            key = (row.get("fact_key") or "", row.get("fact_value") or "")
            if key[0] and key[1]:
                unique_facts.setdefault(key, row)

        summary_rows.append(
            {
                "school_id": school_id,
                "country": pick_mode(countries) or country_from_url(rows[0].get("url")) or "unknown",
                "school_name": pick_mode(school_names) or cleaned_name(rows[0], fallback_url=rows[0].get("url")) or school_id,
                "homepage_url": school_homepage_url_by_school_id.get(school_id) or school_homepage_from_url(rows[0].get("url")) or rows[0].get("url"),
                "page_count": len(rows),
                "fact_count": len(facts),
                "unique_fact_count": len(unique_facts),
                "unique_url_count": len(unique_urls),
                "page_roles": "|".join(sorted(set(page_roles))),
                "page_types": "|".join(sorted(set(page_types))),
                **signal_counts,
            }
        )

        for (fact_key, fact_value), source_row in unique_facts.items():
            school_fact_rows.append(
                {
                    "school_id": school_id,
                    "country": source_row.get("country") or pick_mode(countries) or "unknown",
                    "school_name": pick_mode(school_names) or cleaned_name(rows[0], fallback_url=rows[0].get("url")) or school_id,
                    "homepage_url": school_homepage_url_by_school_id.get(school_id) or school_homepage_from_url(rows[0].get("url")) or rows[0].get("url"),
                    "fact_key": fact_key,
                    "fact_value": fact_value,
                    "source_url": source_row.get("url"),
                    "page_role": normalize_role(source_row),
                    "page_type": source_row.get("page_type"),
                    "crawl_depth": source_row.get("crawl_depth"),
                    "parent_url": source_row.get("parent_url"),
                    "scraped_at": source_row.get("scraped_at"),
                }
            )

    num_id_by_school: dict[str, str] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in summary_rows:
        grouped[country_code_from_value(row.get("country"))].append(row)

    for country_code in sorted(grouped):
        for idx, row in enumerate(sorted(grouped[country_code], key=school_sort_key), start=1):
            num_id_by_school[row["school_id"]] = f"{country_code}{idx:05d}"

    for row in summary_rows:
        row["school_num_id"] = num_id_by_school.get(row["school_id"])
    for row in school_fact_rows:
        row["school_num_id"] = num_id_by_school.get(row["school_id"])

    return summary_rows, school_fact_rows, num_id_by_school, school_page_url_to_id


def build_admission_tables(
    page_rows: list[dict],
    fact_rows: list[dict],
    school_url_to_id: dict[str, str],
    school_name_by_school_id: dict[str, str],
    min_admission_pages: int,
):
    admission_page_rows: list[dict] = []
    admission_pages_by_school_id: dict[str, list[dict]] = defaultdict(list)
    admission_facts_by_school_id: dict[str, list[dict]] = defaultdict(list)

    for row in page_rows:
        role = row.get("page_role") or normalize_role(row)
        if role != "admission":
            continue
        url = row.get("url") or ""
        parent_url = row.get("parent_url") or ""
        school_id = (
            school_url_to_id.get(parent_url)
            or school_url_to_id.get(school_homepage_from_url(url) or "")
            or row.get("school_id")
            or infer_school_id_from_row(row, fallback_url=parent_url or url)
        )
        row["school_id"] = school_id
        admission_page_rows.append(row)
        admission_pages_by_school_id[school_id].append(row)

    for row in fact_rows:
        role = row.get("page_role") or normalize_role(row)
        if role != "admission":
            continue
        cleaned_fact_value = clean_local_currency_text(row.get("fact_value"))
        if not cleaned_fact_value:
            continue
        url = row.get("url") or ""
        parent_url = row.get("parent_url") or ""
        school_id = (
            school_url_to_id.get(parent_url)
            or school_url_to_id.get(school_homepage_from_url(url) or "")
            or row.get("school_id")
            or infer_school_id_from_row(row, fallback_url=parent_url or url)
        )
        row["school_id"] = school_id
        row["fact_value"] = cleaned_fact_value
        admission_facts_by_school_id[school_id].append(row)

    summary_rows: list[dict] = []
    admission_fact_rows: list[dict] = []

    for school_id, rows in admission_pages_by_school_id.items():
        if len(rows) < min_admission_pages:
            continue
        facts = admission_facts_by_school_id.get(school_id, [])
        countries = [r.get("country") for r in rows if r.get("country")]
        page_types = [r.get("page_type") for r in rows if r.get("page_type")]
        page_roles = [r.get("page_role") for r in rows if r.get("page_role")]
        school_names = [school_name_by_school_id.get(r.get("school_id") or "", "") for r in rows]
        unique_urls = sorted({r.get("url") for r in rows if r.get("url")})
        unique_facts: dict[tuple[str, str], dict] = {}
        for row in facts:
            key = (row.get("fact_key") or "", row.get("fact_value") or "")
            if key[0] and key[1]:
                unique_facts.setdefault(key, row)

        summary_rows.append(
            {
                "school_id": school_id,
                "country": pick_mode(countries) or country_from_url(rows[0].get("url")) or "unknown",
                "school_name": pick_mode(school_names) or school_name_by_school_id.get(school_id, "") or "unknown",
                "admission_url": rows[0].get("url"),
                "page_count": len(rows),
                "fact_count": len(facts),
                "unique_fact_count": len(unique_facts),
                "unique_url_count": len(unique_urls),
                "page_roles": "|".join(sorted(set(page_roles))),
                "page_types": "|".join(sorted(set(page_types))),
            }
        )

        for (fact_key, fact_value), source_row in unique_facts.items():
            admission_fact_rows.append(
                {
                    "school_id": school_id,
                    "country": source_row.get("country") or pick_mode(countries) or "unknown",
                    "school_name": school_name_by_school_id.get(source_row.get("school_id") or school_id, "") or "unknown",
                    "admission_url": rows[0].get("url"),
                    "fact_key": fact_key,
                    "fact_value": fact_value,
                    "source_url": source_row.get("url"),
                    "page_role": normalize_role(source_row),
                    "page_type": source_row.get("page_type"),
                    "crawl_depth": source_row.get("crawl_depth"),
                    "parent_url": source_row.get("parent_url"),
                    "scraped_at": source_row.get("scraped_at"),
                }
            )

    num_id_by_school: dict[str, str] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in summary_rows:
        grouped[country_code_from_value(row.get("country"))].append(row)

    for country_code in sorted(grouped):
        for idx, row in enumerate(sorted(grouped[country_code], key=school_sort_key), start=1):
            num_id_by_school[row["school_id"]] = f"{country_code}{idx:05d}"

    for row in summary_rows:
        row["school_num_id"] = num_id_by_school.get(row["school_id"])
    for row in admission_fact_rows:
        row["school_num_id"] = num_id_by_school.get(row["school_id"])

    return summary_rows, admission_fact_rows


def build_program_tables(
    page_rows: list[dict],
    fact_rows: list[dict],
    school_url_to_id: dict[str, str],
    school_name_by_school_id: dict[str, str],
    min_program_pages: int,
):
    program_page_rows: list[dict] = []
    for row in page_rows:
        role = row.get("page_role") or normalize_role(row)
        if role != "program":
            continue
        program_page_rows.append(row)

    program_pages_by_id: dict[str, list[dict]] = defaultdict(list)
    program_facts_by_id: dict[str, list[dict]] = defaultdict(list)
    program_url_by_program_id: dict[str, str] = {}

    for row in program_page_rows:
        url = row.get("url") or ""
        parent_url = row.get("parent_url") or ""
        inferred_school_id = (
            school_url_to_id.get(parent_url)
            or school_url_to_id.get(school_homepage_from_url(url) or "")
            or row.get("school_id")
            or infer_school_id_from_row(row, fallback_url=parent_url or url)
        )
        row["school_id"] = inferred_school_id
        program_name = infer_program_name_from_row(row, fallback_url=url)
        degree_level = infer_degree_level(program_name or row.get("title") or row.get("h1") or url)
        program_level = normalize_program_level(degree_level)
        program_id = infer_program_id(inferred_school_id, row, fallback_url=url)
        row["program_id"] = program_id
        row["program_name"] = program_name
        row["degree_level"] = degree_level or "unknown"
        row["program_level"] = program_level
        program_pages_by_id[program_id].append(row)
        program_url_by_program_id.setdefault(program_id, url)

    for row in fact_rows:
        role = row.get("page_role") or normalize_role(row)
        if role != "program":
            continue
        cleaned_fact_value = clean_local_currency_text(row.get("fact_value"))
        if not cleaned_fact_value:
            continue
        url = row.get("url") or ""
        parent_url = row.get("parent_url") or ""
        derived_program_name = program_name_from_fact_value(row.get("fact_value"))
        if derived_program_name:
            current_guess = row.get("program_name_guess") or ""
            if not current_guess or "courses and fees" in current_guess.lower() or current_guess.lower() == "programs":
                row["program_name_guess"] = derived_program_name
        inferred_school_id = (
            school_url_to_id.get(parent_url)
            or school_url_to_id.get(school_homepage_from_url(url) or "")
            or row.get("school_id")
            or infer_school_id_from_row(row, fallback_url=parent_url or url)
        )
        program_name = infer_program_name_from_row(row, fallback_url=url)
        degree_level = infer_degree_level(program_name or row.get("title") or row.get("h1") or url) or "unknown"
        program_level = normalize_program_level(degree_level)
        program_id = infer_program_id(inferred_school_id, row, fallback_url=url)
        row["school_id"] = inferred_school_id
        row["program_id"] = program_id
        row["program_name"] = program_name
        row["degree_level"] = degree_level
        row["program_level"] = program_level
        row["fact_value"] = cleaned_fact_value
        program_facts_by_id[program_id].append(row)

    summary_rows: list[dict] = []
    program_fact_rows: list[dict] = []
    all_program_ids = sorted(set(program_pages_by_id) | set(program_facts_by_id))
    for program_id in all_program_ids:
        rows = program_pages_by_id.get(program_id, [])
        facts = program_facts_by_id.get(program_id, [])
        if len(rows) < min_program_pages and not facts:
            continue
        countries = [r.get("country") for r in rows if r.get("country")]
        page_types = [r.get("page_type") for r in rows if r.get("page_type")]
        page_roles = [r.get("page_role") for r in rows if r.get("page_role")]
        school_ids = [r.get("school_id") for r in rows if r.get("school_id")]
        school_names = [school_name_by_school_id.get(r.get("school_id") or "", "") for r in rows]
        program_names = [r.get("program_name") for r in rows if r.get("program_name")]
        program_names.extend([r.get("program_name") for r in facts if r.get("program_name")])
        degree_levels = [r.get("degree_level") for r in rows if r.get("degree_level")]
        degree_levels.extend([r.get("degree_level") for r in facts if r.get("degree_level")])
        signal_counts = {field: 0 for field in SIGNAL_FIELDS}
        for row in rows:
            for field in SIGNAL_FIELDS:
                if row.get(field) in {"1", "yes", "true", True}:
                    signal_counts[field] += 1
        for row in facts:
            for field in SIGNAL_FIELDS:
                if row.get(field) in {"1", "yes", "true", True}:
                    signal_counts[field] += 1

        unique_urls = sorted({r.get("url") for r in rows if r.get("url")} | {r.get("url") for r in facts if r.get("url")})
        primary_row = rows[0] if rows else (facts[0] if facts else {})
        program_name_value = pick_mode(program_names) or infer_program_name_from_row(primary_row, fallback_url=primary_row.get("url")) or "unknown"
        degree_level_value = pick_mode(degree_levels) or "unknown"
        program_level_value = normalize_program_level(degree_level_value)
        unique_facts: dict[tuple[str, str], dict] = {}
        for row in facts:
            key = (row.get("fact_key") or "", row.get("fact_value") or "")
            if key[0] and key[1]:
                unique_facts.setdefault(key, row)

        summary_rows.append(
            {
                "program_id": program_id,
                "school_id": pick_mode(school_ids) or "unknown",
                "country": pick_mode(countries) or country_from_url(primary_row.get("url")) or "unknown",
                "school_name": pick_mode(school_names) or school_name_by_school_id.get(pick_mode(school_ids) or "", "") or "unknown",
                "program_url": program_url_by_program_id.get(program_id) or primary_row.get("url"),
                "program_name": program_name_value,
                "degree_level": degree_level_value,
                "program_level": program_level_value,
                "page_count": len(rows),
                "fact_count": len(facts),
                "unique_fact_count": len(unique_facts),
                "unique_url_count": len(unique_urls),
                "page_roles": "|".join(sorted(set(page_roles))),
                "page_types": "|".join(sorted(set(page_types))),
                **signal_counts,
            }
        )

        for (fact_key, fact_value), source_row in unique_facts.items():
            program_fact_rows.append(
                {
                    "program_id": program_id,
                    "school_id": source_row.get("school_id") or pick_mode(school_ids) or "unknown",
                    "country": source_row.get("country") or pick_mode(countries) or "unknown",
                    "school_name": school_name_by_school_id.get(source_row.get("school_id") or pick_mode(school_ids) or "", "") or "unknown",
                    "program_url": program_url_by_program_id.get(program_id) or source_row.get("url"),
                    "program_name": program_name_value,
                    "degree_level": degree_level_value,
                    "program_level": program_level_value,
                    "fact_key": fact_key,
                    "fact_value": fact_value,
                    "source_url": source_row.get("url"),
                    "page_role": normalize_role(source_row),
                    "page_type": source_row.get("page_type"),
                    "crawl_depth": source_row.get("crawl_depth"),
                    "parent_url": source_row.get("parent_url"),
                    "scraped_at": source_row.get("scraped_at"),
                }
            )

    school_num_by_school_id: dict[str, str] = {}
    school_groups: dict[str, list[str]] = defaultdict(list)
    all_school_ids = sorted({row["school_id"] for row in summary_rows if row.get("school_id")})
    for school_id in all_school_ids:
        country = school_id.split("_", 1)[0] if "_" in school_id else "unknown"
        school_groups[country_code_from_value(country)].append(school_id)
    for country_code in sorted(school_groups):
        for idx, school_id in enumerate(sorted(school_groups[country_code]), start=1):
            school_num_by_school_id[school_id] = f"{country_code}{idx:05d}"

    for row in summary_rows:
        row["school_num_id"] = school_num_by_school_id.get(row["school_id"])
    for row in program_fact_rows:
        row["school_num_id"] = school_num_by_school_id.get(row["school_id"])

    return summary_rows, program_fact_rows


def write_csv(path: str, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    page_rows = load_rows(args.pages_csv)
    fact_rows = load_rows(args.facts_csv)

    school_summary_rows, school_fact_rows, school_num_by_school_id, school_url_to_id = build_school_tables(
        page_rows, fact_rows, args.min_school_pages
    )
    school_name_by_school_id = {row["school_id"]: row["school_name"] for row in school_summary_rows if row.get("school_id")}
    admission_summary_rows, admission_fact_rows = build_admission_tables(
        page_rows, fact_rows, school_url_to_id, school_name_by_school_id, args.min_school_pages
    )
    program_summary_rows, program_fact_rows = build_program_tables(
        page_rows, fact_rows, school_url_to_id, school_name_by_school_id, args.min_program_pages
    )

    school_summary_rows.sort(key=school_sort_key)
    school_fact_rows.sort(key=lambda r: (r.get("school_num_id") or "", r.get("fact_key") or "", r.get("fact_value") or ""))
    admission_summary_rows.sort(key=school_sort_key)
    admission_fact_rows.sort(key=lambda r: (r.get("school_num_id") or "", r.get("fact_key") or "", r.get("fact_value") or ""))
    program_summary_rows.sort(key=program_sort_key)
    program_fact_rows.sort(key=lambda r: (r.get("school_num_id") or "", r.get("program_id") or "", r.get("fact_key") or "", r.get("fact_value") or ""))

    write_csv(
        args.school_summary_csv,
        school_summary_rows,
        [
            "school_num_id",
            "school_id",
            "country",
            "school_name",
            "homepage_url",
            "page_count",
            "fact_count",
            "unique_fact_count",
            "unique_url_count",
            "page_roles",
            "page_types",
            *SIGNAL_FIELDS,
        ],
    )
    write_csv(
        args.school_facts_csv,
        school_fact_rows,
        [
            "school_num_id",
            "school_id",
            "country",
            "school_name",
            "homepage_url",
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
    if args.admission_summary_csv:
        write_csv(
            args.admission_summary_csv,
            admission_summary_rows,
            [
                "school_num_id",
                "school_id",
                "country",
                "school_name",
                "admission_url",
                "page_count",
                "fact_count",
                "unique_fact_count",
                "unique_url_count",
                "page_roles",
                "page_types",
            ],
        )
    if args.admission_facts_csv:
        write_csv(
            args.admission_facts_csv,
            admission_fact_rows,
            [
                "school_num_id",
                "school_id",
                "country",
                "school_name",
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
    write_csv(
        args.program_summary_csv,
        program_summary_rows,
        [
            "program_id",
            "school_num_id",
            "school_id",
            "country",
            "school_name",
            "program_url",
            "program_name",
            "degree_level",
            "program_level",
            "page_count",
            "fact_count",
            "unique_fact_count",
            "unique_url_count",
            "page_roles",
            "page_types",
            *SIGNAL_FIELDS,
        ],
    )
    write_csv(
        args.program_facts_csv,
        program_fact_rows,
        [
            "program_id",
            "school_num_id",
            "school_id",
            "country",
            "school_name",
            "program_url",
            "program_name",
            "degree_level",
            "program_level",
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

    if args.school_summary_jsonl:
        write_jsonl(args.school_summary_jsonl, school_summary_rows)
    if args.admission_summary_jsonl:
        write_jsonl(args.admission_summary_jsonl, admission_summary_rows)
    if args.program_summary_jsonl:
        write_jsonl(args.program_summary_jsonl, program_summary_rows)

    print(f"school_summary={len(school_summary_rows)}")
    print(f"school_facts={len(school_fact_rows)}")
    print(f"program_summary={len(program_summary_rows)}")
    print(f"program_facts={len(program_fact_rows)}")


if __name__ == "__main__":
    main()
