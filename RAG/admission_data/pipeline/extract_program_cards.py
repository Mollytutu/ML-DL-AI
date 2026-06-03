import argparse
import csv
import re
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from collegedunia_paths import (
    infer_degree_level,
    normalize_program_level,
    school_homepage_from_url,
    school_homepage_parts,
)
from csv_safety import clean_local_currency_text, normalize_audience_text, sanitize_row
from scrape_collegedunia_selenium import expand_course_lists, make_driver


FOUND_COUNT_RE = re.compile(r"Found\s+(\d+)\s+Courses?", re.I)
DURATION_RE = re.compile(r"\b\d+\s+(?:year|years|month|months)\b", re.I)
CURRENCY_RE = re.compile(r"\b(USD|AUD|CAD|EUR|GBP|AED|HKD|MYR|NZD|SEK)\b")
MONEY_RE = re.compile(
    r"\b(?:USD|AUD|CAD|EUR|GBP|AED|HKD|MYR|NZD|SEK)\s?[0-9][0-9,]*(?:\.[0-9]+)?(?:\s*/\s*(?:Yr|Year))?",
    re.I,
)
YEAR_RE = re.compile(r"\b20\d{2}\b")
NOISE_VALUE_RE = re.compile(
    r"(content curator|updated\s+\d|download brochure|download course details|compare|practice questions|1 on 1 interaction)",
    re.I,
)

EXPECTED_LOCAL_CURRENCY = {
    "australia": "AUD",
    "canada": "CAD",
    "germany": "EUR",
    "hong-kong": "HKD",
    "ireland": "EUR",
    "malaysia": "MYR",
    "netherlands": "EUR",
    "new-zealand": "NZD",
    "sweden": "SEK",
    "uae": "AED",
    "uk": "GBP",
    "usa": "USD",
}
SCHOOL_TITLE_CLEAN_RE = re.compile(
    r"\s*(Courses and Fees|Programs:? Tuition fees, Ranking, Scholarships, Application Deadlines & Entry Requirements).*$",
    re.I,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract one structured row per visible Collegedunia program card.")
    p.add_argument("--urls-file", required=True)
    p.add_argument("--output-csv", required=True)
    p.add_argument("--summary-csv", required=True)
    p.add_argument("--wait-sec", type=float, default=4.0)
    headless_group = p.add_mutually_exclusive_group()
    headless_group.add_argument("--headless", dest="headless", action="store_true")
    headless_group.add_argument("--no-headless", dest="headless", action="store_false")
    p.set_defaults(headless=True)
    p.add_argument("--driver-path")
    p.add_argument("--browser-binary")
    return p.parse_args()


def load_urls(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def normalize_source_url(raw_url: str) -> str:
    text = normalize_text(raw_url)
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme and parsed.netloc:
        parsed = urlparse(f"https://{text}")
    elif not parsed.scheme and parsed.path.startswith("www."):
        parsed = urlparse(f"https://{text}")
    elif not parsed.scheme and not parsed.netloc:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    safe_path = quote(parsed.path or "/", safe="/%:@")
    safe_query = quote(parsed.query or "", safe="=&%:+,.-_")
    return urlunparse((parsed.scheme, parsed.netloc, safe_path, parsed.params, safe_query, ""))


def normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def infer_school_name(url: str, soup: BeautifulSoup) -> str:
    h1 = normalize_text(soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "")
    if h1:
        cleaned = SCHOOL_TITLE_CLEAN_RE.sub("", h1).strip(" :-")
        if cleaned:
            return normalize_audience_text(cleaned)
    parts = school_homepage_parts(url)
    if parts:
        slug = re.sub(r"^\d+-", "", parts.slug).replace("-", " ")
        return normalize_audience_text(normalize_text(slug.title()))
    return ""


def query_degree_type(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    degree_type = normalize_text((query.get("degree_type") or [""])[0])
    if not degree_type:
        return ""
    if degree_type.lower() == "doctorate":
        return "phd"
    if degree_type.lower() in {"diploma certificate", "graduate certificate/graduate diploma"}:
        return "certificate"
    return degree_type.lower()


def infer_program_level_from_title(title: str, query_degree: str) -> tuple[str, str]:
    text = normalize_text(title).lower()
    if query_degree:
        return query_degree, normalize_program_level(query_degree)
    if re.search(r"(ph\.?d|doctorate|doctoral|dphil)", text):
        return "phd", "phd"
    if re.search(r"(graduate certificate|graduate diploma|advanced diploma|diploma|certificate)", text):
        return "certificate", "certificate"
    if re.search(r"(master|m\.?s\.?|m\.?a\.?|mba|llm|mph|msw)", text):
        return "master", "master"
    if re.search(r"(bachelor|b\.?s\.?|b\.?a\.?|b\.?tech|b\.?eng|b\.?sc)", text):
        return "bachelor", "undergrad"
    inferred = infer_degree_level(title) or ""
    return inferred, normalize_program_level(inferred)


def label_value_from_card(card: BeautifulSoup, label_text: str) -> str:
    for block in card.select("div.card-info"):
        label = normalize_text(" ".join(el.get_text(" ", strip=True) for el in block.select("span.text-gray, span.mr-half.text-gray, span.text-title")))
        block_text = normalize_text(block.get_text(" ", strip=True))
        if label_text.lower() not in label.lower() and label_text.lower() not in block_text.lower():
            continue
        if ":" in block_text:
            _, value = block_text.split(":", 1)
            return normalize_text(value)
        return block_text
    return ""


def extract_course_tags(card: BeautifulSoup) -> list[str]:
    tags = []
    for node in card.select("div.course-tags > div, div.course-tags span"):
        text = normalize_text(node.get_text(" ", strip=True))
        if text and text not in tags:
            tags.append(text)
    return tags


def pick_expected_currency_amount(text: str, expected_currency: str) -> tuple[str, str]:
    cleaned = clean_local_currency_text(text)
    if not cleaned:
        return "", ""
    matches = [m.group(0).strip() for m in MONEY_RE.finditer(cleaned)]
    if not matches:
        return "", ""
    if expected_currency:
        for match in reversed(matches):
            currency_match = CURRENCY_RE.search(match)
            if currency_match and currency_match.group(1).upper() == expected_currency:
                return match, expected_currency
        return "", ""
    last = matches[-1]
    currency_match = CURRENCY_RE.search(last)
    return last, (currency_match.group(1).upper() if currency_match else "")


def extract_program_rows(url: str, soup: BeautifulSoup) -> tuple[list[dict], dict]:
    school_name = infer_school_name(url, soup)
    homepage_url = school_homepage_from_url(url) or url
    country = (school_homepage_parts(url).country if school_homepage_parts(url) else "")
    expected_currency = EXPECTED_LOCAL_CURRENCY.get(country, "")
    page_text = normalize_text(soup.get_text("\n", strip=True))
    found_matches = FOUND_COUNT_RE.findall(page_text)
    expected_count = int(found_matches[-1]) if found_matches else 0
    query_degree = query_degree_type(url)

    rows = []
    seen = set()
    cards = soup.select("div.course-card")
    for card in cards:
        title_link = card.select_one("a.text-title[href]")
        program_name = normalize_text(title_link.get_text(" ", strip=True) if title_link else "")
        if not program_name:
            continue
        program_url = urljoin(url, title_link["href"]) if title_link else ""
        card_text = normalize_text(card.get_text(" ", strip=True))
        fees_text = normalize_text(card.select_one("span.fees").get_text(" ", strip=True) if card.select_one("span.fees") else "")
        fees_text, currency = pick_expected_currency_amount(f"{fees_text} {card_text}".strip(), expected_currency)
        duration = ""
        delivery_mode = ""
        language = ""
        study_mode = ""
        course_tags = extract_course_tags(card)
        for tag in course_tags:
            if not duration and DURATION_RE.search(tag):
                duration = tag
            elif not language and tag.lower() in {"english"}:
                language = tag
            elif not study_mode and tag.lower() in {"full time", "part time"}:
                study_mode = tag
            elif not delivery_mode:
                delivery_mode = tag

        important_date = label_value_from_card(card, "Important Date")
        entry_requirement = label_value_from_card(card, "Entry Requirement")
        exam_scores = label_value_from_card(card, "Exam Scores")
        if NOISE_VALUE_RE.search(entry_requirement):
            entry_requirement = ""
        if NOISE_VALUE_RE.search(exam_scores):
            exam_scores = ""

        degree_level, program_level = infer_program_level_from_title(program_name, query_degree)

        row_key = (program_url or program_name, program_name, important_date, fees_text)
        if row_key in seen:
            continue
        seen.add(row_key)

        rows.append(
            {
                "school_name": school_name,
                "country": country,
                "school_homepage_url": homepage_url,
                "source_programs_url": url,
                "program_name": program_name,
                "program_url": program_url,
                "degree_level_raw": degree_level,
                "program_level": program_level,
                "duration": duration,
                "delivery_mode": delivery_mode,
                "language": language,
                "study_mode": study_mode,
                "important_date": important_date,
                "has_deadline": "yes" if important_date and YEAR_RE.search(important_date) else "no",
                "tuition_local": fees_text,
                "currency": currency,
                "entry_requirement": entry_requirement,
                "exam_scores": exam_scores,
            }
        )

    summary = {
        "school_name": school_name,
        "country": country,
        "source_programs_url": url,
        "expected_count": expected_count,
        "extracted_count": len(rows),
        "card_count": len(cards),
        "has_deadline_count": sum(1 for row in rows if row["has_deadline"] == "yes"),
        "has_tuition_count": sum(1 for row in rows if row["tuition_local"]),
        "has_duration_count": sum(1 for row in rows if row["duration"]),
        "has_requirement_count": sum(1 for row in rows if row["entry_requirement"] or row["exam_scores"]),
        "level_breakdown": dict(Counter(row["program_level"] for row in rows)),
    }
    return rows, summary


def write_csv(path: str, rows: list[dict], fieldnames: list[str]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(sanitize_row(row, fieldnames))


def main() -> None:
    args = parse_args()
    urls = [u for u in (normalize_source_url(x) for x in load_urls(args.urls_file)) if u]
    driver = make_driver(headless=args.headless, driver_path=args.driver_path, browser_binary=args.browser_binary)
    wait = WebDriverWait(driver, args.wait_sec)
    rows: list[dict] = []
    summaries: list[dict] = []
    skipped_bad_url = 0

    try:
        for url in urls:
            try:
                driver.get(url)
                wait.until(lambda d: d.execute_script("return document.readyState") in {"interactive", "complete"})
                if not query_degree_type(url):
                    expand_course_lists(driver)
                soup = BeautifulSoup(driver.page_source, "html.parser")
                local_rows, summary = extract_program_rows(url, soup)
                rows.extend(local_rows)
                summaries.append(summary)
            except Exception:
                skipped_bad_url += 1
                continue
    finally:
        driver.quit()

    write_csv(
        args.output_csv,
        rows,
        [
            "school_name",
            "country",
            "school_homepage_url",
            "source_programs_url",
            "program_name",
            "program_url",
            "degree_level_raw",
            "program_level",
            "duration",
            "delivery_mode",
            "language",
            "study_mode",
            "important_date",
            "has_deadline",
            "tuition_local",
            "currency",
            "entry_requirement",
            "exam_scores",
        ],
    )
    write_csv(
        args.summary_csv,
        summaries,
        [
            "school_name",
            "country",
            "source_programs_url",
            "expected_count",
            "extracted_count",
            "card_count",
            "has_deadline_count",
            "has_tuition_count",
            "has_duration_count",
            "has_requirement_count",
            "level_breakdown",
        ],
    )
    print(f"program_rows={len(rows)}")
    print(f"summary_rows={len(summaries)}")
    print(f"skipped_bad_url={skipped_bad_url}")
    print(f"output_csv={args.output_csv}")
    print(f"summary_csv={args.summary_csv}")


if __name__ == "__main__":
    main()
