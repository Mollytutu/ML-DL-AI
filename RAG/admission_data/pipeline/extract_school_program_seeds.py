import argparse
import csv
import json
import re

from collegedunia_paths import (
    infer_degree_level,
    infer_program_id,
    infer_program_name_from_row,
    infer_school_id_from_row,
    infer_school_name_from_row,
    page_role_from_url,
    school_homepage_from_url,
)


SUBUNIT_HINTS = [
    "business school",
    "school of business",
    "school of law",
    "law school",
    "graduate school",
    "school of medicine",
    "school of public health",
    "school of engineering",
    "school of education",
    "school of nursing",
    "school of architecture",
    "school of design",
    "school of journalism",
    "school of international",
    "school of government",
    "school of policy",
    "school of information",
    "school of pharmacy",
    "school of dentistry",
    "school of veterinary",
    "college of arts and sciences",
    "college of engineering",
    "faculty of law",
    "faculty of medicine",
    "faculty of engineering",
    "wharton",
    "booth",
    "sloan",
    "kellogg",
    "ross",
    "fuqua",
    "tuck",
    "stern",
    "anderson",
    "johnson",
    "mccombs",
    "carey",
    "krannert",
    "fisher",
    "rady",
    "haas",
    "kenan",
    "flagler",
    "broad",
    "som",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract deduped school and program seeds from Collegedunia raw URL lists")
    p.add_argument("--in-files", nargs="+", required=True, help="Input raw txt files with URLs")
    p.add_argument("--out-school-csv", required=True)
    p.add_argument("--out-school-txt", required=False)
    p.add_argument("--out-school-jsonl", required=False)
    p.add_argument("--out-program-csv", required=True)
    p.add_argument("--out-program-txt", required=False)
    p.add_argument("--out-program-jsonl", required=False)
    p.add_argument("--out-subunit-csv", required=False)
    p.add_argument("--out-subunit-txt", required=False)
    return p.parse_args()


def load_urls(paths: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                url = line.strip()
                if url:
                    out.append((path, url))
    return out


def normalize_slugish(text: str | None) -> str:
    t = (text or "").lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_subunit_school(url: str) -> bool:
    home = school_homepage_from_url(url)
    if not home:
        return False
    hint = normalize_slugish(infer_school_name_from_row({"url": url}, fallback_url=url))
    path = normalize_slugish(url)
    haystack = f"{hint} {path}"
    return any(token in haystack for token in SUBUNIT_HINTS)


def country_from_home(home: str) -> str:
    parts = home.split("/")
    if len(parts) >= 4:
        return parts[3]
    return ""


def main() -> None:
    args = parse_args()
    rows = load_urls(args.in_files)

    school_seen: dict[str, dict] = {}
    subunit_seen: dict[str, dict] = {}
    program_seen: dict[str, dict] = {}

    for source_file, url in rows:
        page_role = page_role_from_url(url)
        if page_role == "other":
            continue

        if page_role == "program":
            home = school_homepage_from_url(url)
            if not home:
                continue
            school_row = {"url": home}
            program_row = {"url": url}
            school_id = infer_school_id_from_row(school_row, fallback_url=home)
            program_id = infer_program_id(school_id, program_row, fallback_url=url)
            seed_kind = "program_index" if infer_program_name_from_row(program_row, fallback_url=url) == "Programs" else "program_detail"
            program_seen.setdefault(
                program_id,
                {
                    "program_id": program_id,
                    "school_id": school_id,
                    "country": country_from_home(home),
                    "school_name": infer_school_name_from_row(school_row, fallback_url=home),
                    "program_url": url,
                    "program_name": infer_program_name_from_row(program_row, fallback_url=url),
                    "degree_level": infer_degree_level(url) or "unknown",
                    "seed_kind": seed_kind,
                    "source_file": source_file,
                },
            )
            target = subunit_seen if is_subunit_school(home) else school_seen
            target.setdefault(
                home,
                {
                    "school_id": school_id,
                    "country": country_from_home(home),
                    "school_name": infer_school_name_from_row(school_row, fallback_url=home),
                    "homepage_url": home,
                    "seed_kind": "subunit_homepage" if is_subunit_school(home) else "school_homepage",
                    "source_file": source_file,
                },
            )
            continue

        home = school_homepage_from_url(url)
        if not home:
            continue

        school_row = {"url": home}
        school_id = infer_school_id_from_row(school_row, fallback_url=home)
        row_data = {
            "school_id": school_id,
            "country": country_from_home(home),
            "school_name": infer_school_name_from_row(school_row, fallback_url=home),
            "homepage_url": home,
            "seed_kind": "subunit_homepage" if is_subunit_school(home) else "school_homepage",
            "source_file": source_file,
        }
        if is_subunit_school(home):
            subunit_seen.setdefault(home, row_data)
        else:
            school_seen.setdefault(home, row_data)

    school_rows = sorted(
        school_seen.values(),
        key=lambda r: (r.get("country") or "", r.get("school_name") or "", r.get("homepage_url") or ""),
    )
    program_rows = sorted(
        program_seen.values(),
        key=lambda r: (
            r.get("country") or "",
            r.get("school_name") or "",
            r.get("program_name") or "",
            r.get("program_url") or "",
        ),
    )
    subunit_rows = sorted(
        subunit_seen.values(),
        key=lambda r: (r.get("country") or "", r.get("school_name") or "", r.get("homepage_url") or ""),
    )

    def write_csv(path: str, rows: list[dict], fieldnames: list[str]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def write_txt(path: str, rows: list[dict], key: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                val = row.get(key)
                if val:
                    f.write(val + "\n")

    def write_jsonl(path: str, rows: list[dict]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    write_csv(
        args.out_school_csv,
        school_rows,
        ["school_id", "country", "school_name", "homepage_url", "seed_kind", "source_file"],
    )
    write_csv(
        args.out_program_csv,
        program_rows,
        ["program_id", "school_id", "country", "school_name", "program_url", "program_name", "degree_level", "seed_kind", "source_file"],
    )
    if args.out_subunit_csv:
        write_csv(
            args.out_subunit_csv,
            subunit_rows,
            ["school_id", "country", "school_name", "homepage_url", "seed_kind", "source_file"],
        )
    if args.out_school_txt:
        write_txt(args.out_school_txt, school_rows, "homepage_url")
    if args.out_program_txt:
        write_txt(args.out_program_txt, program_rows, "program_url")
    if args.out_subunit_txt:
        write_txt(args.out_subunit_txt, subunit_rows, "homepage_url")
    if args.out_school_jsonl:
        write_jsonl(args.out_school_jsonl, school_rows)
    if args.out_program_jsonl:
        write_jsonl(args.out_program_jsonl, program_rows)

    print(f"school_seeds={len(school_rows)}")
    print(f"program_seeds={len(program_rows)}")
    print(f"subunit_seeds={len(subunit_rows)}")


if __name__ == "__main__":
    main()
