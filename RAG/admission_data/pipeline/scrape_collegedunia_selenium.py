import argparse
import csv
import os
import re
import time
from datetime import datetime, timezone
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from collegedunia_paths import is_review_url, school_homepage_parts
from csv_safety import clean_local_currency_text, normalize_audience_text

try:
    from webdriver_manager.chrome import ChromeDriverManager
except Exception:  # pragma: no cover - optional dependency for local fallback
    ChromeDriverManager = None

MONEY_TOKEN_RE = re.compile(r"(₹|INR|USD|AUD|CAD|EUR|GBP|\$|£|€)\s?[0-9][0-9,]*(?:\.[0-9]+)?", re.I)
DEADLINE_RE = re.compile(r"(deadline|last date|application closes?|apply by|closing date)", re.I)
EXAM_RE = re.compile(r"(ielts|toefl|pte|sat|act|gre|gmat|duolingo)", re.I)
NOISE_RE = re.compile(
    r"(study abroad|get upto|get up to|discount on visa fees|visa fees|course finder|apply now|get college details|compare|fees history|programs? & fees|advisor|advisors?|counsell?ing|counselor|college predictor|practice questions|top engineering colleges|top management colleges|top medical colleges|college notifications|about collegedunia|download the collegedunia app|1 on 1 interaction|how likely are you to recommend collegedunia|want help or need to review a college|top universities & colleges|read college reviews|collegedunia team|do you think the fees are wrong|study in [a-z -]+ > colleges? in [a-z -]+ > .* > programs|\\(enrolled\\s+20\\d{2}\\))",
    re.I,
)
WORD_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
SUMMARY_BANNED_RE = re.compile(
    r"(you can apply|recommended is|you may face|there is a requirement|gurantor|guarantor|studapart|airbnb|hostels?|commutation|platform i used|cheap stay|rent|apartment|visa|accommodation)",
    re.I,
)
SUMMARY_PROGRAM_SNIPPET_RE = re.compile(
    r"(this course focuses on|as tabulated below|popular courses among|cost 20\d{2}|program fees)",
    re.I,
)
REVIEW_SECTION_RE = re.compile(
    r"^(students?[’']?\s*reviews?\s+from\s+reddit(?:\s+and\s+collegedunia)?|student reviews?\s+from\s+reddit(?:\s+and\s+collegedunia)?|raw student reviews?|user reviews?)[:\s]*$",
    re.I,
)
RAW_REVIEW_TITLE_RE = re.compile(r"(\breview at\b|my honest review|don't take admission)", re.I)
RAW_REVIEW_BODY_RE = re.compile(r"\b(i chose|i was|i applied|my experience|my college life|my review|enrolled\s+20\d{2})\b", re.I)

FACT_PATTERNS = {
    "tuition": re.compile(r"(tuition|fee|fees|cost|expenses?)", re.I),
    "deadline": DEADLINE_RE,
    "exam_requirement": EXAM_RE,
    "eligibility": re.compile(r"(eligibility|entry requirement|admission requirement)", re.I),
    "applications_count": re.compile(r"(applications|applicants|total applicants)", re.I),
    "admitted_count": re.compile(r"(admitted|offers made|admissions offered)", re.I),
    "acceptance_rate": re.compile(r"(acceptance rate|admit rate|admission rate)", re.I),
    "enrolled_count": re.compile(r"(enrolled|matriculated|freshman class|incoming class)", re.I),
    "yield_rate": re.compile(r"(yield rate|enrollment yield)", re.I),
    "intake": re.compile(r"(intake|start date|session)", re.I),
    "duration": re.compile(r"(duration|year|semester|month)", re.I),
    "ranking": re.compile(r"(ranking|ranked)", re.I),
    "scholarship": re.compile(r"(scholarship|financial aid|funding|fellowship|grant|bursary|assistantship|tuition waiver|stipend)", re.I),
}

SUMMARY_KEYWORDS = ("university", "college", "school", "institute")
SUMMARY_MIN_WORDS = 300
SUMMARY_MAX_WORDS = 50000
SUMMARY_TARGET_WORDS = 4000
SUMMARY_MAX_PARAGRAPHS = 180
SCHOLARSHIP_MAX_WORDS = 1500
SCHOLARSHIP_MAX_CHARS = 16000
SUMMARY_TOGGLE_TOKENS = (
    "read more",
    "readmore",
    "show more",
    "see more",
    "view more",
)
HOME_TAB_TOKENS = ("home",)

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

KNOWN_COUNTRY_SLUGS = {
    "australia",
    "canada",
    "france",
    "georgia",
    "germany",
    "hong-kong",
    "hungary",
    "india",
    "ireland",
    "italy",
    "japan",
    "kazakhstan",
    "kyrgyzstan",
    "malaysia",
    "netherlands",
    "new-zealand",
    "philippines",
    "russia",
    "singapore",
    "south-africa",
    "spain",
    "sweden",
    "switzerland",
    "uae",
    "uk",
    "usa",
    "uzbekistan",
}

TARGET_HINTS = (
    "/university/",
    "/course/",
    "/courses/",
    "/programs",
    "/admission",
    "/fees",
    "/tuition",
    "/requirement",
    "/eligibility",
    "/deadline",
    "/scholarship",
    "/ranking",
)
FALLBACK_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
INDIA_TOKEN_RE = re.compile(r"\b(?:india|indian)\b", re.I)
INR_ARTIFACT_RE = re.compile(r"\b(?:inr|rs\.?|rupees?|lakh|lakhs|crore|crores)\b", re.I)
LPA_TOKEN_RE = re.compile(r"\b\d+(?:\.\d+)?\s*L(?:/Yr|/Year)?\b", re.I)


def money_signal_without_inr(text: str) -> str | None:
    t = normalize_text(text)
    matches = list(MONEY_TOKEN_RE.finditer(t))
    for match in matches:
        token = (match.group(1) or "").upper()
        if token not in {"INR", "₹"}:
            return match.group(0)
    return None


def strip_inr_currency_text(text: str) -> str:
    return clean_local_currency_text(text)


def apply_text_filters(text: str) -> str:
    """Remove India/INR wording and currency artifacts."""
    t = normalize_text(text)
    if not t:
        return ""
    t = strip_inr_currency_text(t)
    t = t.replace("₹", " ")
    t = INR_ARTIFACT_RE.sub(" ", t)
    t = INDIA_TOKEN_RE.sub(" ", t)
    t = LPA_TOKEN_RE.sub(" ", t)
    return normalize_text(t)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Selenium scraper for Collegedunia (CSV output)")
    p.add_argument("--urls-file", required=True)
    p.add_argument("--pages-csv", required=True)
    p.add_argument("--facts-csv", required=True)
    p.add_argument("--max-pages", type=int, default=20)
    p.add_argument("--wait-sec", type=float, default=3.0)
    headless_group = p.add_mutually_exclusive_group()
    headless_group.add_argument("--headless", dest="headless", action="store_true")
    headless_group.add_argument("--no-headless", dest="headless", action="store_false", help="Run Chrome with a visible window.")
    p.set_defaults(headless=True)
    p.add_argument("--driver-path", default=os.environ.get("CHROMEDRIVER_PATH"))
    p.add_argument("--browser-binary", default=os.environ.get("CHROME_BINARY"))
    p.add_argument("--crawl-depth", type=int, default=1, help="How many link hops to follow from each seed URL.")
    p.add_argument("--max-child-links-per-page", type=int, default=150)
    p.add_argument("--max-facts-per-page", type=int, default=80)
    p.add_argument("--max-line-len", type=int, default=260)
    p.add_argument("--min-line-len", type=int, default=12)
    p.add_argument(
        "--facts-mode",
        choices=["all", "school_homepage"],
        default="all",
        help="Which page types should produce extracted facts.",
    )
    return p.parse_args()


def load_urls(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def word_count(text: str) -> int:
    return len(WORD_TOKEN_RE.findall(text or ""))


def trim_to_max_words(text: str, max_words: int) -> str:
    words = WORD_TOKEN_RE.findall(text or "")
    if len(words) <= max_words:
        return normalize_text(text or "")
    trimmed = " ".join(words[:max_words]).strip()
    return normalize_text(trimmed)


def clean_summary_text(text: str) -> str:
    """Remove obvious non-summary junk sentences from extracted summary blocks."""
    parts = re.split(r"(?<=[.!?])\s+", normalize_text(text))
    kept: list[str] = []
    for sent in parts:
        s = normalize_text(sent)
        if not s:
            continue
        if SUMMARY_BANNED_RE.search(s) or SUMMARY_PROGRAM_SNIPPET_RE.search(s):
            continue
        kept.append(s)
    return normalize_text(" ".join(kept))


def extract_cdcms_article_summary(soup: BeautifulSoup) -> str:
    """Extract full school article text from Collegedunia cdcms_* blocks when present.

    Keep full textual content order and avoid aggressive dedup/trim so long-form pages
    (including admissions/scholarship sections) are preserved as completely as possible.
    """
    blocks = []
    for div in soup.find_all("div"):
        classes = div.get("class") or []
        if not any(str(cls).startswith("cdcms_") for cls in classes):
            continue
        blocks.append(div)

    if not blocks:
        return ""

    lines: list[str] = []
    for block in blocks:
        for tag in block(["script", "style"]):
            tag.decompose()
        for node in block.find_all(["h2", "h3", "p", "li", "th", "td"]):
            # Preserve original text wording in summary blocks.
            line = normalize_text(node.get_text(" ", strip=True))
            line = apply_text_filters(line)
            if not line:
                continue
            lines.append(line)

    summary = normalize_text(" ".join(lines))
    return summary


def fetch_raw_html_for_summary(url: str, timeout_sec: int = 20) -> str:
    """Lightweight fallback fetch when Selenium page_source misses long cdcms summary blocks."""
    try:
        req = Request(url, headers={"User-Agent": FALLBACK_UA})
        with urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read()
        return raw.decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, ValueError):
        return ""
    except Exception:
        return ""


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def country_code_from_value(value: str | None) -> str:
    raw = (value or "unknown").strip().lower()
    if raw in COUNTRY_CODE_OVERRIDES:
        return COUNTRY_CODE_OVERRIDES[raw]
    letters = re.sub(r"[^a-z]+", "", raw)
    if not letters:
        return "UN"
    if len(letters) >= 2:
        return letters[:2].upper()
    return (letters.upper() + "X")[:2]


def school_name_from_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = normalize_text(text)
    cleaned = cleaned.split(":", 1)[0].strip()
    cleaned = re.sub(r"\s*-\s*(admissions?|fees?|rankings?|scholarships?|courses?|programs?).*$", "", cleaned, flags=re.I).strip()
    return cleaned or None


def school_slug_from_url(url: str) -> str:
    parts = school_homepage_parts(url)
    if parts:
        slug = re.sub(r"^\d+-", "", parts.slug)
        return slug or "unknown_school"
    path = urlparse(url).path.strip("/")
    if not path:
        return "unknown_school"
    slug = path.split("/")[-1]
    slug = re.sub(r"^\d+-", "", slug)
    slug = re.sub(r"-(admissions?|fees?|rankings?|scholarships?|courses?|programs?)\b.*$", "", slug, flags=re.I)
    slug = re.sub(r"-(admissions?|fees?|rankings?|scholarships?|courses?|programs?)$", "", slug, flags=re.I)
    return slug or "unknown_school"


def classify_page(url: str) -> str:
    u = url.lower()
    if is_review_url(url):
        return "school_review"
    if "/admission" in u:
        return "admission"
    if "/course/" in u or "/programs" in u:
        return "program"
    if "/university/" in u:
        return "university"
    if "/college/" in u:
        return "college"
    if "/institute/" in u or "/school/" in u:
        return "institute"
    return "other"


def country_from_url(url: str) -> str | None:
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    first = path.split("/")[0].lower()
    if first in KNOWN_COUNTRY_SLUGS:
        return first
    if first in {"university", "college", "institute", "school"}:
        return "india"
    return None


def school_id_from(
    url: str,
    country: str | None,
    school_name_guess: str | None,
    h1: str | None,
    parent_url: str | None = None,
) -> str:
    base = school_name_from_text(school_name_guess) or school_name_from_text(h1)
    if not base:
        source_url = parent_url or url
        base = school_slug_from_url(source_url)
    prefix = country or "unknown"
    return f"{prefix}_{slugify(base)}"


def normalize_url(base: str, href: str | None) -> str | None:
    if not href:
        return None
    url = urljoin(base, href)
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "collegedunia.com":
        return None
    if any(ext in url.lower() for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".pdf", ".zip", ".mp4", ".mov")):
        return None
    return url


def is_relevant_url(url: str, anchor_text: str = "") -> bool:
    u = url.lower()
    t = anchor_text.lower()
    if "ratings" in t or re.search(r"\b(student reviews?|user reviews?|reddit)\b", t):
        return False
    if any(k in t for k in ("view all courses", "show more", "show all", "load more", "all courses", "courses & fees", "programs & fees")):
        return True
    return any(h in u for h in TARGET_HINTS) or any(k in t for k in ("tuition", "fee", "fees", "deadline", "requirement", "eligibility", "admission", "scholarship", "ranking", "courses", "programs"))


def is_program_child_url(url: str, anchor_text: str = "") -> bool:
    u = url.lower()
    t = anchor_text.lower()
    return (
        "/programs" in u
        or "/course/" in u
        or "view all courses" in t
        or "all courses" in t
        or "courses & fees" in t
        or "program" in t
        or "course" in t
    )


def should_extract_facts(page_type: str, facts_mode: str) -> bool:
    if facts_mode == "school_homepage":
        return page_type in {"university", "college", "institute", "school", "admission", "school_review"}
    return page_type != "review"


def is_raw_student_review_page(url: str, title: str | None, h1: str | None, full_text: str) -> bool:
    combined = normalize_text(" ".join(part for part in [title, h1] if part))
    signals = 0
    if "review" in (url or "").lower():
        signals += 1
    if RAW_REVIEW_TITLE_RE.search(combined):
        signals += 1
    if RAW_REVIEW_BODY_RE.search(full_text[:4000]):
        signals += 1
    if re.search(r"\b(review|ratings?)\b", combined.lower()):
        signals += 1
    return signals >= 2 and not re.search(r"\b(top|overview|ranking|fees|courses)\b", combined.lower())


def discover_child_urls(soup: BeautifulSoup, base_url: str, max_links: int, source_page_type: str | None = None) -> list[str]:
    program_urls: list[str] = []
    other_urls: list[str] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        child = normalize_url(base_url, a.get("href"))
        if not child or child in seen:
            continue
        anchor_text = normalize_text(a.get_text(" ", strip=True))
        if not is_relevant_url(child, anchor_text):
            continue
        seen.add(child)
        if source_page_type == "admission" and is_program_child_url(child, anchor_text):
            continue
        if is_program_child_url(child, anchor_text):
            program_urls.append(child)
        else:
            other_urls.append(child)

    if max_links <= 0:
        return program_urls + other_urls
    if len(program_urls) >= max_links:
        return program_urls
    return program_urls + other_urls[: max_links - len(program_urls)]


def expand_course_lists(driver: webdriver.Chrome, max_clicks: int = 14) -> None:
    """Click obvious course-expansion controls so hidden program links become visible."""
    try:
        source_text = normalize_text(driver.page_source or "").lower()
    except Exception:
        source_text = ""
    if not any(
        token in source_text
        for token in (
            "view all courses",
            "view all course",
            "show more",
            "show all",
            "load more",
            "all courses",
            "courses & fees",
            "programs & fees",
            "all programs",
        )
    ):
        return

    for _ in range(max_clicks):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, "a, button, [role='button']")
        except Exception:
            return
        clicked = False
        for element in elements:
            try:
                label = normalize_text(element.text).lower()
            except Exception:
                label = ""
            if not label:
                continue
            if not any(token in label for token in ("view all courses", "view all course", "show more", "show all", "load more", "all courses", "courses & fees", "programs & fees", "all programs")):
                continue
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.2)
                element.click()
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", element)
                except Exception:
                    continue
            time.sleep(0.8)
            clicked = True
            break
        if not clicked:
            break


def activate_home_tab(driver: webdriver.Chrome, max_clicks: int = 2) -> None:
    """Prefer the school Home tab before extracting homepage facts."""
    for _ in range(max_clicks):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, "a, button, [role='tab'], [role='button']")
        except Exception:
            return
        clicked = False
        for element in elements:
            try:
                label = normalize_text(element.text).lower()
            except Exception:
                label = ""
            if label not in HOME_TAB_TOKENS:
                continue
            try:
                outer_html = (element.get_attribute("outerHTML") or "").lower()
            except Exception:
                outer_html = ""
            if "breadcrumb" in outer_html or "home page" in outer_html:
                continue
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.2)
                element.click()
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", element)
                except Exception:
                    continue
            time.sleep(1.0)
            clicked = True
            break
        if not clicked:
            break


def expand_school_summaries(driver: webdriver.Chrome, max_clicks: int = 20) -> None:
    """Expand truncated school summary blocks so page_source contains full intro text."""
    try:
        source_text = normalize_text(driver.page_source or "").lower()
    except Exception:
        source_text = ""
    if not any(token in source_text for token in SUMMARY_TOGGLE_TOKENS):
        return

    for _ in range(max_clicks):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, "a, button, [role='button'], span, div")
        except Exception:
            return
        clicked = False
        for element in elements:
            try:
                label = normalize_text(element.text).lower()
            except Exception:
                label = ""
            if not label or not any(token in label for token in SUMMARY_TOGGLE_TOKENS):
                continue
            try:
                outer_html = (element.get_attribute("outerHTML") or "").lower()
            except Exception:
                outer_html = ""
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.2)
                element.click()
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", element)
                except Exception:
                    continue
            time.sleep(0.8)
            clicked = True
            break
        if not clicked:
            break


def assign_school_num_ids(rows: list[dict]) -> dict[str, str]:
    school_ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        school_id = row.get("school_id") or "unknown"
        if school_id not in seen:
            seen.add(school_id)
            school_ids.append(school_id)

    grouped: dict[str, list[str]] = {}
    for school_id in school_ids:
        country = school_id.split("_", 1)[0] if "_" in school_id else "unknown"
        grouped.setdefault(country_code_from_value(country), []).append(school_id)

    mapping: dict[str, str] = {}
    for country_code in sorted(grouped):
        for idx, school_id in enumerate(sorted(grouped[country_code]), start=1):
            mapping[school_id] = f"{country_code}{idx:05d}"
    return mapping


def signals_from_text(text: str) -> dict[str, str | None]:
    t = normalize_text(text)
    money = money_signal_without_inr(t)
    pct = re.search(r"\b\d{1,3}(?:\.\d+)?\s?%", t)
    return {
        "money_signal": money,
        "percent_signal": pct.group(0) if pct else None,
        "has_deadline_signal": "yes" if DEADLINE_RE.search(t) else "no",
        "has_exam_signal": "yes" if EXAM_RE.search(t) else "no",
        "has_acceptance_signal": "yes" if FACT_PATTERNS["acceptance_rate"].search(t) else "no",
        "has_applications_signal": "yes" if FACT_PATTERNS["applications_count"].search(t) else "no",
        "has_admitted_signal": "yes" if FACT_PATTERNS["admitted_count"].search(t) else "no",
        "has_enrolled_signal": "yes" if FACT_PATTERNS["enrolled_count"].search(t) else "no",
        "has_yield_signal": "yes" if FACT_PATTERNS["yield_rate"].search(t) else "no",
    }


def extract_scholarship_sections(soup: BeautifulSoup) -> list[str]:
    """Extract scholarship-focused sections (can be long-form, 500+ words)."""
    nodes = soup.find_all(["h2", "h3", "h4", "h5", "h6", "p", "li", "th", "td"])
    ordered: list[tuple[str, str]] = []
    for node in nodes:
        line = normalize_text(node.get_text(" ", strip=True))
        line = normalize_audience_text(apply_text_filters(line))
        if not line:
            continue
        ordered.append((node.name.lower(), line))

    out: list[str] = []
    seen: set[str] = set()
    heading_tags = {"h2", "h3", "h4", "h5", "h6"}
    scholarship_rx = FACT_PATTERNS["scholarship"]

    for idx, (tag, line) in enumerate(ordered):
        if tag not in heading_tags or not scholarship_rx.search(line):
            continue
        section_lines = [line]
        words = word_count(line)
        for j in range(idx + 1, len(ordered)):
            tag2, line2 = ordered[j]
            if tag2 in heading_tags:
                break
            if NOISE_RE.search(line2):
                continue
            section_lines.append(line2)
            words += word_count(line2)
            if words >= SCHOLARSHIP_MAX_WORDS:
                break
        block = normalize_text(" ".join(section_lines))
        if not block:
            continue
        if word_count(block) > SCHOLARSHIP_MAX_WORDS:
            block = trim_to_max_words(block, SCHOLARSHIP_MAX_WORDS)
        if len(block) > SCHOLARSHIP_MAX_CHARS:
            block = block[:SCHOLARSHIP_MAX_CHARS].rstrip()
        if block not in seen:
            seen.add(block)
            out.append(block)

    # Fallback: keep individual scholarship lines when no heading-structured section was found.
    if not out:
        for _, line in ordered:
            if not scholarship_rx.search(line):
                continue
            if len(line) > SCHOLARSHIP_MAX_CHARS:
                line = line[:SCHOLARSHIP_MAX_CHARS].rstrip()
            if line not in seen:
                seen.add(line)
                out.append(line)
    return out


def extract_facts(
    soup: BeautifulSoup,
    min_len: int,
    max_len: int,
    max_facts: int,
    page_type: str = "other",
) -> list[tuple[str, str]]:
    for tag in soup(["script", "style", "svg", "noscript", "iframe", "video", "img", "picture", "source", "canvas"]):
        tag.decompose()

    # Drop obvious student review / Reddit review sections before text extraction.
    for tag in soup.find_all(["h2", "h3", "h4", "strong", "b", "div"]):
        heading = normalize_text(tag.get_text(" ", strip=True))
        if not heading or not REVIEW_SECTION_RE.search(heading):
            continue
        # Remove the nearest visible section block when possible; otherwise remove the node itself.
        container = tag
        for _ in range(4):
            parent = container.parent
            if not parent or getattr(parent, "name", None) in {"body", "html"}:
                break
            text = normalize_text(parent.get_text(" ", strip=True))
            if len(text) >= len(heading) and REVIEW_SECTION_RE.search(text):
                container = parent
            else:
                break
        container.decompose()

    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    if page_type == "school_review":
        summary_key = "school_review"
    elif page_type == "admission":
        summary_key = "admission_summary"
    else:
        summary_key = "school_summary"
    summary_eligible = page_type in {"university", "college", "institute", "school", "admission", "school_review"}
    summary_added = False

    # Preferred path: pull full "Read More About The University" article blocks.
    if summary_eligible:
        cdcms_summary = extract_cdcms_article_summary(soup)
        if cdcms_summary and word_count(cdcms_summary) >= SUMMARY_MIN_WORDS:
            pair = (summary_key, cdcms_summary)
            seen.add(pair)
            out.append(pair)
            summary_added = True
            if len(out) >= max_facts:
                return out

    # Fallback path for pages without cdcms_* long-form sections.
    if summary_eligible and not summary_added:
        nodes = [tag for tag in soup.find_all(["h2", "h3", "p", "li", "th", "td"])]
        summary_candidates: list[str] = []
        for tag in nodes:
            line = normalize_text(tag.get_text(" ", strip=True))
            line = apply_text_filters(line)
            if not line:
                continue
            summary_candidates.append(line)
            if len(summary_candidates) >= SUMMARY_MAX_PARAGRAPHS:
                break

        summary_text = normalize_text(" ".join(summary_candidates))
        if summary_text:
            wc = word_count(summary_text)
            if wc > SUMMARY_MAX_WORDS:
                summary_text = trim_to_max_words(summary_text, SUMMARY_MAX_WORDS)
                wc = word_count(summary_text)
            if wc >= SUMMARY_MIN_WORDS:
                pair = (summary_key, summary_text)
                if pair not in seen:
                    seen.add(pair)
                    out.append(pair)
                if len(out) >= max_facts:
                    return out

    # Dedicated scholarship pass: try to capture full scholarship section text.
    if page_type in {"university", "college", "institute", "school"}:
        for scholarship_text in extract_scholarship_sections(soup):
            pair = ("scholarship", scholarship_text)
            if pair in seen:
                continue
            seen.add(pair)
            out.append(pair)
            if len(out) >= max_facts:
                return out

    # tables first
    for tr in soup.select("table tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th and td:
            k = normalize_text(th.get_text(" ", strip=True))
            v = normalize_text(td.get_text(" ", strip=True))
        else:
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            k = normalize_text(tds[0].get_text(" ", strip=True))
            v = normalize_text(tds[1].get_text(" ", strip=True))
        if not k or not v:
            continue
        if NOISE_RE.search(k) or NOISE_RE.search(v):
            continue
        v = normalize_audience_text(apply_text_filters(v))
        if not v:
            continue
        key = "school_review_highlight" if page_type == "school_review" else "table_field"
        if page_type != "school_review":
            for label, rx in FACT_PATTERNS.items():
                if rx.search(k):
                    key = label
                    break
        clip_len = SCHOLARSHIP_MAX_CHARS if key == "scholarship" else max_len
        if len(v) > clip_len:
            if clip_len <= 3:
                v = v[:clip_len]
            else:
                v = v[: clip_len - 3].rstrip() + "..."
        pair = (key, f"{k}: {v}")
        if pair not in seen:
            seen.add(pair)
            out.append(pair)
        if len(out) >= max_facts:
            return out

    # text lines
    for tag in soup.find_all(["p", "li", "h2", "h3", "h4", "span"]):
        line = normalize_text(tag.get_text(" ", strip=True))
        if not line or len(line) < min_len:
            continue
        is_scholarship_line = bool(FACT_PATTERNS["scholarship"].search(line))
        if len(line) > max_len and not is_scholarship_line:
            continue
        if NOISE_RE.search(line):
            continue
        line = normalize_audience_text(apply_text_filters(line))
        if not line or len(line) < min_len:
            continue
        if is_scholarship_line and len(line) > SCHOLARSHIP_MAX_CHARS:
            line = line[:SCHOLARSHIP_MAX_CHARS].rstrip()
        if page_type == "school_review":
            key = "school_review_highlight"
            if len(line) < max(40, min_len):
                continue
        else:
            key = None
            for label, rx in FACT_PATTERNS.items():
                if rx.search(line):
                    key = label
                    break
            # Keep additional long-form school details so school_pages stays comprehensive
            # even when a line does not match strict keyword patterns.
            if not key and page_type in {"university", "college", "institute", "school"} and len(line) >= max(40, min_len):
                key = "school_detail"
        if not key:
            continue
        pair = (key, line)
        if pair in seen:
            continue
        seen.add(pair)
        out.append(pair)
        if len(out) >= max_facts:
            break

    return out


def is_soft_error_page(html: str) -> bool:
    text = normalize_text(BeautifulSoup(html or "", "lxml").get_text(" ", strip=True)).lower()
    return (
        "the request could not be satisfied" in text
        or "403 error" in text
        or "generated by cloudfront" in text
        or "request blocked" in text
    )


def make_driver(headless: bool, driver_path: str | None = None, browser_binary: str | None = None) -> webdriver.Chrome:
    # Use undetected_chromedriver by default to reduce anti-bot blocking.
    opts = uc.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.page_load_strategy = "eager"
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-software-rasterizer")
    opts.add_argument("--window-size=1440,2200")
    opts.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    opts.set_capability("goog:loggingPrefs", {"browser": "SEVERE"})

    uc_kwargs = {"options": opts}
    if driver_path:
        uc_kwargs["driver_executable_path"] = driver_path
    if browser_binary:
        uc_kwargs["browser_executable_path"] = browser_binary
    try:
        driver = uc.Chrome(**uc_kwargs)
    except TypeError:
        # Compatibility path for older uc versions.
        if browser_binary:
            opts.binary_location = browser_binary
        driver = uc.Chrome(options=opts)
    except Exception:
        # Final fallback: regular webdriver.
        fallback_opts = Options()
        if headless:
            fallback_opts.add_argument("--headless=new")
        if browser_binary:
            fallback_opts.binary_location = browser_binary
        fallback_opts.page_load_strategy = "eager"
        fallback_opts.add_argument("--disable-blink-features=AutomationControlled")
        fallback_opts.add_argument("--no-sandbox")
        fallback_opts.add_argument("--disable-dev-shm-usage")
        fallback_opts.add_argument("--disable-gpu")
        fallback_opts.add_argument("--disable-software-rasterizer")
        fallback_opts.add_argument("--window-size=1440,2200")
        fallback_opts.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        fallback_opts.set_capability("goog:loggingPrefs", {"browser": "SEVERE"})
        if driver_path:
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=fallback_opts)
        else:
            try:
                driver = webdriver.Chrome(options=fallback_opts)
            except Exception:
                if ChromeDriverManager is None:
                    raise
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=fallback_opts)

    driver.set_page_load_timeout(45)
    driver.implicitly_wait(2)
    return driver


def main() -> None:
    args = parse_args()
    headless = args.headless
    seed_urls = load_urls(args.urls_file)
    if args.facts_mode == "school_homepage":
        if args.max_facts_per_page == 80:
            args.max_facts_per_page = 600
        if args.max_line_len == 260:
            args.max_line_len = 1200

    driver = make_driver(headless=headless, driver_path=args.driver_path, browser_binary=args.browser_binary)
    pages: list[dict] = []
    facts: list[dict] = []
    queue: deque[tuple[str, int, str | None]] = deque((u, 0, None) for u in seed_urls)
    visited: set[str] = set()

    try:
        while queue and (args.max_pages <= 0 or len(pages) < args.max_pages):
            url, depth, parent_url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            scraped_at = datetime.now(timezone.utc).isoformat()
            status_code = 0
            html = ""
            title = None
            h1 = None

            try:
                driver.get(url)
                WebDriverWait(driver, args.wait_sec).until(
                    lambda d: d.execute_script("return document.readyState") in {"interactive", "complete"}
                )
                page_type = classify_page(url)
                if page_type in {"university", "college", "institute", "school"}:
                    activate_home_tab(driver)
                    expand_school_summaries(driver, max_clicks=20)
                expand_course_lists(driver, max_clicks=14)
                if page_type in {"university", "college", "institute", "school"}:
                    expand_school_summaries(driver, max_clicks=20)
                html = driver.page_source or ""
                status_code = 200 if html else 0

                try:
                    title = normalize_text(driver.title)
                except Exception:
                    title = None

                try:
                    h1_els = driver.find_elements(By.TAG_NAME, "h1")
                    if h1_els:
                        h1 = normalize_text(h1_els[0].text)
                except Exception:
                    h1 = None
            except Exception:
                status_code = 0

            page_type = classify_page(url)
            country = country_from_url(url)
            school_name = h1 if page_type in {"university", "college", "institute"} else None
            program_name = h1 if page_type == "program" else None
            school_id = school_id_from(
                url,
                country,
                school_name,
                h1 if page_type in {"university", "college", "institute", "school"} else None,
                parent_url,
            )
            local_facts: list[tuple[str, str]] = []
            signals = {
                "money_signal": None,
                "percent_signal": None,
                "has_deadline_signal": "no",
                "has_exam_signal": "no",
                "has_acceptance_signal": "no",
                "has_applications_signal": "no",
                "has_admitted_signal": "no",
                "has_enrolled_signal": "no",
                "has_yield_signal": "no",
            }

            if html:
                if is_soft_error_page(html):
                    status_code = 403
                    html = ""
                else:
                    soup = BeautifulSoup(html, "lxml")
                    text = normalize_text(soup.get_text(" ", strip=True))[:10000]
                    if page_type == "school_review" and is_raw_student_review_page(url, title, h1, text):
                        page_type = "review"
                        local_facts = []
                    else:
                        signals = signals_from_text(text)
                        if should_extract_facts(page_type, args.facts_mode):
                            local_facts = extract_facts(
                                soup,
                                min_len=args.min_line_len,
                                max_len=args.max_line_len,
                                max_facts=args.max_facts_per_page,
                                page_type=page_type,
                            )
                            # Some school homepages return partial DOM to Selenium; backfill summary from raw HTML.
                            has_summary = any(k in {"school_summary", "school_review"} for k, _ in local_facts)
                            if (
                                not has_summary
                                and page_type in {"university", "college", "institute", "school"}
                            ):
                                raw_html = fetch_raw_html_for_summary(url)
                                if raw_html:
                                    raw_soup = BeautifulSoup(raw_html, "lxml")
                                    raw_summary = extract_cdcms_article_summary(raw_soup)
                                    if raw_summary:
                                        wc = word_count(raw_summary)
                                        if wc > SUMMARY_MAX_WORDS:
                                            raw_summary = trim_to_max_words(raw_summary, SUMMARY_MAX_WORDS)
                                            wc = word_count(raw_summary)
                                        if wc >= SUMMARY_MIN_WORDS:
                                            local_facts.insert(0, ("school_summary", raw_summary))
                        if depth < args.crawl_depth:
                            child_urls = discover_child_urls(soup, url, args.max_child_links_per_page, page_type)
                            for child_url in child_urls:
                                if child_url not in visited:
                                    queue.append((child_url, depth + 1, url))

            pages.append(
                {
                    "url": url,
                    "parent_url": parent_url,
                    "crawl_depth": depth,
                    "school_id": school_id,
                    "status_code": status_code,
                    "page_type": page_type,
                    "country": country,
                    "school_name_guess": school_name,
                    "program_name_guess": program_name,
                    "title": title,
                    "h1": h1,
                    "money_signal": signals["money_signal"],
                    "percent_signal": signals["percent_signal"],
                    "has_deadline_signal": signals["has_deadline_signal"],
                    "has_exam_signal": signals["has_exam_signal"],
                    "has_acceptance_signal": signals["has_acceptance_signal"],
                    "has_applications_signal": signals["has_applications_signal"],
                    "has_admitted_signal": signals["has_admitted_signal"],
                    "has_enrolled_signal": signals["has_enrolled_signal"],
                    "has_yield_signal": signals["has_yield_signal"],
                    "fact_count": len(local_facts),
                    "scraped_at": scraped_at,
                }
            )

            for k, v in local_facts:
                facts.append(
                    {
                        "url": url,
                        "parent_url": parent_url,
                        "crawl_depth": depth,
                        "school_id": school_id,
                        "page_type": page_type,
                        "country": country,
                        "school_name_guess": school_name,
                        "program_name_guess": program_name,
                        "fact_key": k,
                        "fact_value": v,
                        "scraped_at": scraped_at,
                    }
                )

            if len(pages) % 100 == 0:
                print(f"processed={len(pages)} queue={len(queue)} visited={len(visited)} facts={len(facts)}")

            time.sleep(0.15)

    finally:
        driver.quit()

    school_num_id_by_school_id = assign_school_num_ids(pages)
    for row in pages:
        row["school_num_id"] = school_num_id_by_school_id.get(row.get("school_id") or "unknown")
    for row in facts:
        row["school_num_id"] = school_num_id_by_school_id.get(row.get("school_id") or "unknown")

    with open(args.pages_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "url", "school_num_id", "school_id", "parent_url", "crawl_depth", "status_code", "page_type", "country", "school_name_guess", "program_name_guess",
                "title", "h1", "money_signal", "percent_signal", "has_deadline_signal", "has_exam_signal",
                "has_acceptance_signal", "has_applications_signal", "has_admitted_signal", "has_enrolled_signal",
                "has_yield_signal", "fact_count", "scraped_at",
            ],
        )
        w.writeheader()
        w.writerows(pages)

    with open(args.facts_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "url", "school_num_id", "school_id", "parent_url", "crawl_depth", "page_type", "country", "school_name_guess", "program_name_guess", "fact_key", "fact_value", "scraped_at",
            ],
        )
        w.writeheader()
        w.writerows(facts)

    print(f"pages={len(pages)}")
    print(f"facts={len(facts)}")
    print(f"pages_csv={args.pages_csv}")
    print(f"facts_csv={args.facts_csv}")


if __name__ == "__main__":
    main()
