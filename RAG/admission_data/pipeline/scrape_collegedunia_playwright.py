import argparse
import csv
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from bs4.element import Tag

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from collegedunia_paths import school_homepage_parts
from csv_safety import clean_local_currency_text, normalize_audience_text


MONEY_TOKEN_RE = re.compile(r"(₹|INR|USD|AUD|CAD|EUR|GBP|\$|£|€)\s?[0-9][0-9,]*(?:\.[0-9]+)?", re.I)
DEADLINE_RE = re.compile(r"(deadline|last date|application closes?|apply by|closing date)", re.I)
EXAM_RE = re.compile(r"(ielts|toefl|pte|sat|act|gre|gmat|duolingo)", re.I)
TUITION_RE = re.compile(r"(tuition|fee|fees|cost|expenses?)", re.I)
ELIGIBILITY_RE = re.compile(r"(eligibility|entry requirement|admission requirement)", re.I)
INTAKE_RE = re.compile(r"(intake|intakes|start date|session)", re.I)
NOISE_RE = re.compile(
    r"(study abroad|get upto|get up to|discount on visa fees|visa fees|course finder|apply now|get college details|compare|fees history|programs? & fees|advisor|advisors?|counsell?ing|counselor|college predictor|practice questions|top engineering colleges|top management colleges|top medical colleges|college notifications|about collegedunia|download the collegedunia app|1 on 1 interaction|how likely are you to recommend collegedunia|want help or need to review a college|top universities & colleges|read college reviews|collegedunia team|do you think the fees are wrong|study in [a-z -]+ > colleges? in [a-z -]+ > .* > programs|\(enrolled\s+20\d{2}\))",
    re.I,
)
REVIEW_SECTION_RE = re.compile(
    r"^(students?[’']?\s*reviews?\s+from\s+reddit(?:\s+and\s+collegedunia)?|student reviews?\s+from\s+reddit(?:\s+and\s+collegedunia)?|raw student reviews?|user reviews?)[:\s]*$",
    re.I,
)
RAW_REVIEW_TITLE_RE = re.compile(r"(\breview at\b|my honest review|don't take admission)", re.I)
RAW_REVIEW_BODY_RE = re.compile(r"\b(i chose|i was|i applied|my experience|my college life|my review|enrolled\s+20\d{2})\b", re.I)
DURATION_RE = re.compile(r"(duration|year|semester|month)", re.I)
PERCENT_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s?%")
ACCEPT_RE = re.compile(r"(acceptance rate|admit rate|admission rate|selection rate)", re.I)
APPLICATIONS_RE = re.compile(r"(applications|applicants|total applicants)", re.I)
ADMITTED_RE = re.compile(r"(admitted|admissions offered|offers made|students admitted)", re.I)
ENROLLED_RE = re.compile(r"(enrolled|matriculated|incoming class|freshman class|first[- ]year intake)", re.I)
YIELD_RE = re.compile(r"(yield rate|enrollment yield)", re.I)


FACT_PATTERNS = {
    "school_summary": re.compile(r"(^.{0,80}(university|college|school|institute).{0,120}$)", re.I),
    "tuition": TUITION_RE,
    "deadline": DEADLINE_RE,
    "exam_requirement": EXAM_RE,
    "eligibility": ELIGIBILITY_RE,
    "intake": INTAKE_RE,
    "duration": DURATION_RE,
    "applications_count": APPLICATIONS_RE,
    "admitted_count": ADMITTED_RE,
    "acceptance_rate": ACCEPT_RE,
    "enrolled_count": ENROLLED_RE,
    "yield_rate": YIELD_RE,
    "ranking": re.compile(r"(ranking|ranked)", re.I),
    "scholarship": re.compile(r"(scholarship|financial aid|funding)", re.I),
}

SUMMARY_KEYWORDS = ("university", "college", "school", "institute")
SUMMARY_TOGGLE_TOKENS = ("read more", "show more", "see more", "more", "view more")
HOME_TAB_TOKENS = ("home",)
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
SUMMARY_CONTAINER_HINT_RE = re.compile(
    r"(content curator|read more about (the )?(university|college|institute|school)|read less|highlights|programs?, campus|residence|rankings?|cost of attendance|scholarships?|alumni|admission requirements?)",
    re.I,
)
ADMISSION_CONTAINER_HINT_RE = re.compile(
    r"(admission requirements?|application fee|deadlines?|how to apply|cost of attendance|financial aid|international students?|admission highlights?)",
    re.I,
)
SUMMARY_LINE_TAGS = ("h1", "h2", "h3", "h4", "p", "li", "td", "th")
SUMMARY_NAV_EXACT_SKIP = {
    "home",
    "courses & fees",
    "ranking",
    "admission",
    "scholarship",
    "reviews",
    "placements",
    "programs",
    "news",
    "gallery",
}
INDIAN_TEXT_RE = re.compile(r"\b(indian|india)\b", re.I)
INDIAN_CURRENCY_RE = re.compile(r"(₹|INR|\blakh\b|\bcrore\b)", re.I)
READ_MORE_ABOUT_RE = re.compile(r"^read more about (the )?(university|college|institute|school)$", re.I)
READ_LESS_ABOUT_RE = re.compile(r"^read less about (the )?(university|college|institute|school)$", re.I)

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
    p = argparse.ArgumentParser(description="Scrape Collegedunia using Playwright and export compact text CSV")
    p.add_argument("--urls-file", required=True)
    p.add_argument("--pages-csv", required=True)
    p.add_argument("--facts-csv", required=True)
    p.add_argument("--max-pages", type=int, default=0)
    p.add_argument("--wait-sec", type=float, default=None, help="Compatibility alias for wait-ms in seconds.")
    p.add_argument("--wait-ms", type=int, default=3000)
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--max-facts-per-page", type=int, default=80)
    p.add_argument("--max-line-len", type=int, default=260)
    p.add_argument("--min-line-len", type=int, default=12)
    p.add_argument("--facts-mode", choices=["all", "school_homepage"], default="all")
    p.add_argument("--crawl-depth", type=int, default=0, help="Accepted for runner compatibility; ignored by Playwright scraper.")
    p.add_argument("--max-child-links-per-page", type=int, default=0, help="Accepted for runner compatibility; ignored by Playwright scraper.")
    return p.parse_args()


def load_urls(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def should_block_request(request) -> bool:
    if request.resource_type in BLOCKED_RESOURCE_TYPES:
        return True
    lowered = request.url.lower()
    return any(lowered.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".mp4", ".mov", ".woff", ".woff2", ".ttf"))


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


def school_slug_tokens(url: str) -> set[str]:
    slug = school_slug_from_url(url)
    parts = [p for p in slug.split("_") if p and p not in {"university", "college", "institute", "school", "of", "at", "the"}]
    return set(parts)


def classify_page(url: str) -> str:
    u = url.lower()
    if "/admission" in u:
        return "admission"
    if re.search(r"(^|/)(reviews?|ratings?)(/|$)", u) or "review-and-ratings" in u:
        return "school_review"
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
    if first in {
        "india",
        "usa",
        "uk",
        "canada",
        "australia",
        "germany",
        "ireland",
        "new-zealand",
        "france",
        "netherlands",
        "singapore",
        "switzerland",
        "italy",
        "japan",
        "hong-kong",
        "uae",
        "malaysia",
        "spain",
        "south-africa",
    }:
        return first
    if first in {"university", "college", "institute", "school"}:
        return "india"
    return None


def school_id_from(url: str, country: str | None, school_name_guess: str | None, program_name_guess: str | None, h1: str | None) -> str:
    base = school_name_from_text(school_name_guess) or school_name_from_text(program_name_guess) or school_name_from_text(h1)
    if not base:
        base = school_slug_from_url(url)
    prefix = country or "unknown"
    return f"{prefix}_{slugify(base)}"


def is_raw_student_review_page(url: str, title: str | None, h1: str | None, full_text: str) -> bool:
    combined = normalize_text(" ".join(part for part in [title, h1] if part))
    lowered_title = combined.lower()
    lowered_url = (url or "").lower()
    # Guard against false positives from normal school pages that merely contain
    # review sections near the bottom. We only treat as review-takeover when:
    # 1) URL itself is review/rating path, or
    # 2) title/h1 strongly indicates a standalone review page.
    if re.search(r"(^|/)(reviews?|ratings?)(/|$)", lowered_url):
        return True
    if RAW_REVIEW_TITLE_RE.search(combined):
        return True
    if re.search(r"\b(review at|my honest review|don't take admission)\b", lowered_title):
        return True
    # Body-only cues are noisy on regular pages; do not classify by body text alone.
    _ = full_text  # reserved for future stricter heuristics if needed
    return False


def is_school_identity_mismatch(url: str, title: str | None, h1: str | None) -> bool:
    expected = school_slug_tokens(url)
    if not expected:
        return False
    combined = normalize_text(" ".join(part for part in [title, h1] if part)).lower()
    if not combined:
        return True
    hits = sum(1 for token in expected if token in combined)
    return hits == 0 and len(expected) >= 2


def guess_entities(url: str, title: str | None, h1: str | None) -> tuple[str | None, str | None]:
    """Best-effort guess of school/program names from h1/title/url."""
    text = h1 or title or ""
    text = normalize_text(text)
    school = None
    program = None

    if " - " in text:
        left, right = text.split(" - ", 1)
        if any(k in right.lower() for k in ["university", "college", "institute"]):
            program = left.strip()
            school = right.strip()
    if school is None and any(k in text.lower() for k in ["university", "college", "institute"]):
        school = text

    page_type = classify_page(url)
    if page_type == "program" and program is None:
        program = text or None
    if page_type in {"university", "college", "institute"} and school is None:
        school = text or None

    return school, program


def text_signals(text: str) -> dict[str, str | None]:
    t = normalize_text(text)
    m = money_signal_without_inr(t)
    pct = PERCENT_RE.search(t)
    return {
        "money_signal": m if m else None,
        "percent_signal": pct.group(0) if pct else None,
        "has_deadline_signal": "yes" if DEADLINE_RE.search(t) else "no",
        "has_exam_signal": "yes" if EXAM_RE.search(t) else "no",
        "has_acceptance_signal": "yes" if ACCEPT_RE.search(t) else "no",
        "has_applications_signal": "yes" if APPLICATIONS_RE.search(t) else "no",
        "has_admitted_signal": "yes" if ADMITTED_RE.search(t) else "no",
        "has_enrolled_signal": "yes" if ENROLLED_RE.search(t) else "no",
        "has_yield_signal": "yes" if YIELD_RE.search(t) else "no",
    }


def extract_table_facts(soup: BeautifulSoup, max_line_len: int, page_type: str = "other") -> list[tuple[str, str]]:
    facts: list[tuple[str, str]] = []
    for tr in soup.select("table tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th and td:
            key = normalize_text(th.get_text(" ", strip=True))
            value = normalize_text(td.get_text(" ", strip=True))
        else:
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            key = normalize_text(tds[0].get_text(" ", strip=True))
            value = normalize_text(tds[1].get_text(" ", strip=True))

        if not key or not value:
            continue
        if NOISE_RE.search(key) or NOISE_RE.search(value):
            continue
        value = normalize_audience_text(strip_inr_currency_text(value))
        if not value:
            continue
        if len(value) > max_line_len:
            value = value[: max_line_len - 3].rstrip() + "..."

        low_key = key.lower()
        fact_key = "school_review_highlight" if page_type == "school_review" else "table_field"
        if page_type != "school_review":
            for label, rx in FACT_PATTERNS.items():
                if label == "school_summary":
                    # school_summary must come from dedicated long-form summary extraction only
                    continue
                if rx.search(low_key):
                    fact_key = label
                    break

        facts.append((fact_key, f"{key}: {value}"))
    return facts


def extract_text_facts(
    soup: BeautifulSoup,
    min_line_len: int,
    max_line_len: int,
    max_facts: int,
    page_type: str = "other",
) -> list[tuple[str, str]]:
    facts: list[tuple[str, str]] = []
    seen: set[str] = set()
    summary_max_line_len = max(max_line_len, 4000)
    summary_key = "school_review" if page_type == "school_review" else ("admission_summary" if page_type == "admission" else "school_summary")
    summary_requires_school_signal = page_type not in {"admission", "school_review"}
    
    def normalize_summary_line(raw_line: str) -> str:
        line = normalize_text(raw_line)
        if not line or len(line) > summary_max_line_len:
            return ""
        if NOISE_RE.search(line):
            return ""
        line = normalize_audience_text(strip_inr_currency_text(line))
        if not line:
            return ""
        if INDIAN_TEXT_RE.search(line):
            return ""
        if INDIAN_CURRENCY_RE.search(line):
            return ""
        lowered = line.lower()
        if lowered in SUMMARY_NAV_EXACT_SKIP:
            return ""
        if lowered in {"read less", "read more"}:
            return ""
        if READ_MORE_ABOUT_RE.search(lowered) or READ_LESS_ABOUT_RE.search(lowered):
            return ""
        return line

    def summary_chunk_from_container(container) -> str:
        lines: list[str] = []
        local_seen: set[str] = set()
        words = 0
        for tag in container.find_all(SUMMARY_LINE_TAGS):
            line = normalize_summary_line(tag.get_text(" ", strip=True))
            if not line:
                continue
            lowered = line.lower()
            if lowered in local_seen:
                continue
            local_seen.add(lowered)
            lines.append(line)
            words += len(line.split())
            if words >= 16000:
                break
        return normalize_text(" ".join(lines))

    def extract_top_school_summary_by_read_less() -> tuple[str, bool]:
        # For school home pages, honor the explicit UI contract:
        # summary content is the block above "Read Less About the University".
        if page_type not in {"university", "college", "institute", "school"}:
            return "", False
        read_less_nodes: list[Tag] = []
        for node in soup.find_all(["a", "button", "span", "div", "p"]):
            txt = normalize_text(node.get_text(" ", strip=True))
            if txt and READ_LESS_ABOUT_RE.search(txt.lower()):
                read_less_nodes.append(node)
        if not read_less_nodes:
            return "", False

        best_text = ""
        for boundary_node in read_less_nodes:
            # Choose a tight container around the read-less boundary.
            container = None
            for parent in [boundary_node, *list(boundary_node.parents)]:
                if not isinstance(parent, Tag):
                    continue
                if parent.name not in {"article", "main", "section", "div"}:
                    continue
                raw = normalize_text(parent.get_text(" ", strip=True)).lower()
                wc = len(raw.split())
                if wc < 40 or wc > 24000:
                    continue
                if "read more about" in raw or "read less about" in raw or "content curator" in raw:
                    container = parent
                    break
            if container is None:
                continue

            # Collect visible text tags before the read-less node in document order.
            lines: list[str] = []
            seen_local: set[str] = set()
            for node in container.descendants:
                if node is boundary_node:
                    break
                if not isinstance(node, Tag):
                    continue
                if node.name not in SUMMARY_LINE_TAGS:
                    continue
                line = normalize_summary_line(node.get_text(" ", strip=True))
                if not line:
                    continue
                lowered = line.lower()
                if lowered in seen_local:
                    continue
                seen_local.add(lowered)
                lines.append(line)

            text = normalize_text(" ".join(lines))
            if len(text.split()) < 30:
                continue
            if len(text) > len(best_text):
                best_text = text
        return best_text, True

    def extract_summary_chunk() -> str:
        # For school/admission pages, prefer the full expanded article container
        # so summary is stored as a complete chunk instead of fragmented lines.
        if page_type == "school_review":
            return ""
        strict_school_summary, has_read_less_boundary = extract_top_school_summary_by_read_less()
        # If read-less boundary exists, enforce strict boundary extraction only.
        # Do not fall back to broader summary scraping on this page.
        if has_read_less_boundary:
            return strict_school_summary
        if strict_school_summary:
            return strict_school_summary

        container_hint = ADMISSION_CONTAINER_HINT_RE if page_type == "admission" else SUMMARY_CONTAINER_HINT_RE
        best_text = ""
        best_score = -1.0

        for node in soup.find_all(["article", "main", "section", "div"]):
            raw = normalize_text(node.get_text(" ", strip=True))
            if not raw:
                continue
            lowered = raw.lower()
            wc = len(raw.split())
            if wc < 80 or wc > 24000:
                continue
            if "subscribe to our news letter" in lowered:
                continue
            if "download the collegedunia app" in lowered:
                continue
            if not container_hint.search(lowered):
                continue

            text = summary_chunk_from_container(node)
            if not text:
                continue
            text_wc = len(text.split())
            if text_wc < 40:
                continue

            score = float(text_wc) / 120.0
            if "content curator" in lowered:
                score += 40.0
            if "read less" in lowered:
                score += 25.0
            if "read more about the" in lowered:
                score += 20.0
            if "highlights" in lowered:
                score += 12.0
            if any(token in lowered for token in SUMMARY_KEYWORDS):
                score += 8.0
            if page_type == "admission" and ("admission requirements" in lowered or "application fee" in lowered):
                score += 15.0
            if "students also viewed" in lowered:
                score -= 10.0

            if score > best_score:
                best_score = score
                best_text = text

        if best_text:
            return best_text

        # Fallback: keep everything from primary text tags to avoid missing summary words.
        return summary_chunk_from_container(soup)

    summary_chunk = extract_summary_chunk()
    if summary_chunk:
        lowered = summary_chunk.lower()
        if lowered not in seen and len(summary_chunk.split()) >= 30:
            seen.add(lowered)
            facts.append((summary_key, summary_chunk))
            if len(facts) >= max_facts:
                return facts

    paragraphs = [tag for tag in soup.find_all(["p", "li", "h2", "h3", "h4", "td", "th"])]
    summary_candidates: list[str] = []
    summary_started = False
    for tag in paragraphs:
        line = normalize_text(tag.get_text(" ", strip=True))
        if not line:
            continue
        if len(line) < max(40, min_line_len) or len(line) > summary_max_line_len:
            continue
        if NOISE_RE.search(line):
            continue
        line = normalize_audience_text(strip_inr_currency_text(line))
        if not line:
            continue
        lowered = line.lower()
        has_summary_signal = any(token in lowered for token in SUMMARY_KEYWORDS)
        if not summary_started:
            if summary_requires_school_signal and not has_summary_signal:
                continue
            summary_started = True
        elif has_summary_signal:
            pass
        elif summary_requires_school_signal and len(line) < 180 and not re.search(r"\b(it|they|the university|the college|the school|the institute|its|their|this university|this college|this school|this institute)\b", lowered):
            continue
        if line not in summary_candidates:
            summary_candidates.append(line)
        if len(summary_candidates) >= 300:
            break

    summary_word_est = len(" ".join(summary_candidates).split()) if summary_candidates else 0
    if summary_word_est < 1200:
        body_text = soup.get_text("\n", strip=True)
        body_lines = [normalize_text(line) for line in body_text.split("\n")]
        fallback_candidates: list[str] = []
        for line in body_lines:
            if not line:
                continue
            if len(line) > summary_max_line_len:
                continue
            line = normalize_audience_text(strip_inr_currency_text(line))
            if not line:
                continue
            if NOISE_RE.search(line):
                continue
            lowered = line.lower()
            word_count = len(line.split())
            if word_count < 12:
                continue
            if not re.search(r"[.?!]", line):
                continue
            if lowered in {"home", "reviews", "reviews?", "key highlights"}:
                continue
            if re.fullmatch(r"(location|school type|estd\d+|established year|enrollment|public|private|partner.*|reviews?|get free counselling|home|courses & fees|ranking|gallery|scholarship|admission|placements|accommodation|student profiles|news)", lowered):
                continue
            has_summary_signal = any(token in lowered for token in SUMMARY_KEYWORDS)
            if summary_requires_school_signal and not fallback_candidates and not has_summary_signal:
                # if the page is a review-first page, allow the first actual prose paragraph after metadata
                if not re.search(r"(university|college|school|institute)", lowered):
                    continue
            if line not in fallback_candidates:
                fallback_candidates.append(line)
            if len(fallback_candidates) >= 160:
                break

        if fallback_candidates:
            for line in fallback_candidates:
                if line not in summary_candidates:
                    summary_candidates.append(line)

    if summary_candidates and not summary_chunk:
        summary_text = normalize_text(" ".join(summary_candidates))
        if len(summary_text.split()) >= 30:
            lowered = summary_text.lower()
            if lowered not in seen:
                seen.add(lowered)
                facts.append((summary_key, summary_text))
                if len(facts) >= max_facts:
                    return facts

    for tag in soup.find_all(["p", "li", "h2", "h3", "h4", "span"]):
        line = normalize_text(tag.get_text(" ", strip=True))
        if not line:
            continue
        if len(line) < min_line_len or len(line) > max_line_len:
            continue
        if NOISE_RE.search(line):
            continue
        line = normalize_audience_text(strip_inr_currency_text(line))
        if not line or len(line) < min_line_len:
            continue

        if page_type == "school_review":
            fact_key = "school_review_highlight"
            if len(line) < max(40, min_line_len):
                continue
        else:
            fact_key = None
            for label, rx in FACT_PATTERNS.items():
                if rx.search(line):
                    fact_key = label
                    break
            if fact_key == "school_summary":
                # Summary is already captured as a long-form block above.
                continue
        if fact_key is None:
            continue

        if line.lower() in seen:
            continue
        seen.add(line.lower())
        facts.append((fact_key, line))

        if len(facts) >= max_facts:
            break

    return facts


def keep_text_only_dom(soup: BeautifulSoup) -> None:
    # Remove non-text-heavy or noisy elements to keep outputs small and text-only useful.
    for tag in soup(["script", "style", "svg", "noscript", "iframe", "video", "img", "picture", "source", "canvas"]):
        tag.decompose()
    for tag in soup.find_all(["h2", "h3", "h4", "strong", "b", "div"]):
        heading = normalize_text(tag.get_text(" ", strip=True))
        if not heading or not REVIEW_SECTION_RE.search(heading):
            continue
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


def expand_school_summaries(page, max_clicks: int = 4) -> None:
    locator_candidates = [
        page.get_by_role(
            "button",
            name=re.compile(r"read more about (the )?(university|college|institute|school)", re.I),
        ),
        page.get_by_role(
            "link",
            name=re.compile(r"read more about (the )?(university|college|institute|school)", re.I),
        ),
        page.get_by_text(
            re.compile(r"^read more about (the )?(university|college|institute|school)$", re.I)
        ),
    ]
    for locator in locator_candidates:
        for _ in range(max_clicks):
            try:
                if locator.count() <= 0:
                    break
                handle = locator.first
                handle.scroll_into_view_if_needed(timeout=1000)
                handle.click(timeout=1000)
                page.wait_for_timeout(250)
            except Exception:
                break

    try:
        source_text = normalize_text(page.content() or "").lower()
    except Exception:
        source_text = ""
    if not any(token in source_text for token in SUMMARY_TOGGLE_TOKENS):
        return
    for _ in range(max_clicks):
        clicked = False
        try:
            handles = page.locator("a, button, [role='button']").evaluate_all(
                """els => els.map(el => ({
                    text: (el.innerText || '').trim(),
                    html: (el.outerHTML || '').toLowerCase()
                }))"""
            )
        except Exception:
            return
        for idx, item in enumerate(handles):
            try:
                label = normalize_text(item.get("text") or "").lower()
                outer_html = item.get("html") or ""
            except Exception:
                continue
            if not label or label not in SUMMARY_TOGGLE_TOKENS:
                continue
            # Only click summary toggles inside article-like containers.
            if not any(token in outer_html for token in ("content curator", "read less", "about the university", "about the college", "about the institute", "about the school", "highlights")):
                continue
            if "course" in outer_html or "program" in outer_html:
                continue
            # Avoid review/rating expansion links; they can navigate away from school-home content.
            if "review" in label or "rating" in label:
                continue
            if "review" in outer_html or "rating" in outer_html:
                continue
            try:
                handle = page.locator("a, button, [role='button']").nth(idx)
                handle.scroll_into_view_if_needed()
                page.wait_for_timeout(50)
                handle.click(timeout=800)
            except Exception:
                continue
            page.wait_for_timeout(150)
            clicked = True
            break
        if not clicked:
            break


def activate_home_tab(page, max_clicks: int = 1) -> None:
    locator_candidates = [
        page.get_by_role("tab", name=re.compile(r"^home$", re.I)),
        page.get_by_role("link", name=re.compile(r"^home$", re.I)),
        page.get_by_role("button", name=re.compile(r"^home$", re.I)),
        page.get_by_text(re.compile(r"^home$", re.I)),
    ]
    for locator in locator_candidates:
        try:
            if locator.count() <= 0:
                continue
            handle = locator.first
            handle.scroll_into_view_if_needed(timeout=1000)
            handle.click(timeout=1000)
            page.wait_for_timeout(250)
            return
        except Exception:
            continue

    for _ in range(max_clicks):
        clicked = False
        try:
            handles = page.locator("a, button, [role='tab'], [role='button']").evaluate_all(
                """els => els.map(el => ({
                    text: (el.innerText || '').trim(),
                    html: (el.outerHTML || '').toLowerCase()
                }))"""
            )
        except Exception:
            return
        for idx, item in enumerate(handles):
            try:
                label = normalize_text(item.get("text") or "").lower()
                outer_html = item.get("html") or ""
            except Exception:
                continue
            if label not in HOME_TAB_TOKENS:
                continue
            if "breadcrumb" in outer_html or "home page" in outer_html:
                continue
            try:
                handle = page.locator("a, button, [role='tab'], [role='button']").nth(idx)
                handle.scroll_into_view_if_needed()
                page.wait_for_timeout(50)
                handle.click(timeout=800)
            except Exception:
                continue
            page.wait_for_timeout(150)
            clicked = True
            break
        if not clicked:
            break


def is_soft_error_page(text: str) -> bool:
    lowered = normalize_text(text).lower()
    return (
        "the request could not be satisfied" in lowered
        or "403 error" in lowered
        or "generated by cloudfront" in lowered
        or "request blocked" in lowered
    )


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


def write_pages_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "url",
                "school_num_id",
                "school_id",
                "status_code",
                "page_type",
                "country",
                "school_name_guess",
                "program_name_guess",
                "title",
                "h1",
                "money_signal",
                "percent_signal",
                "has_deadline_signal",
                "has_exam_signal",
                "has_acceptance_signal",
                "has_applications_signal",
                "has_admitted_signal",
                "has_enrolled_signal",
                "has_yield_signal",
                "fact_count",
                "scraped_at",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_facts_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "url",
                "school_num_id",
                "school_id",
                "page_type",
                "country",
                "school_name_guess",
                "program_name_guess",
                "fact_key",
                "fact_value",
                "scraped_at",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    urls = load_urls(args.urls_file)
    if args.wait_sec is not None:
        args.wait_ms = int(round(args.wait_sec * 1000))
    if args.max_facts_per_page == 80:
        args.max_facts_per_page = 300
    if args.max_line_len == 260:
        args.max_line_len = 800
    if args.max_pages > 0:
        urls = urls[: args.max_pages]

    page_rows: list[dict] = []
    fact_rows: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        )
        context.set_default_navigation_timeout(12000)
        context.set_default_timeout(3000)
        context.on("dialog", lambda dialog: dialog.dismiss())
        context.route("**/*", lambda route, request: route.abort() if should_block_request(request) else route.continue_())
        for i, url in enumerate(urls, start=1):
            scraped_at = datetime.now(timezone.utc).isoformat()
            status_code = 0
            html = ""
            title = None
            h1 = None
            page_type = classify_page(url)
            country = country_from_url(url)
            school_guess = None
            program_guess = None
            local_facts: list[tuple[str, str]] = []
            money_signal = None
            percent_signal = None
            has_deadline_signal = "no"
            has_exam_signal = "no"
            has_acceptance_signal = "no"
            has_applications_signal = "no"
            has_admitted_signal = "no"
            has_enrolled_signal = "no"
            has_yield_signal = "no"

            def scrape_once() -> tuple[int, str, str | None, str | None, str, str | None, str | None, list[tuple[str, str]], str | None, str | None, str, str, str, str, str, str, str]:
                page = context.new_page()
                local_status = 0
                local_html = ""
                local_title = None
                local_h1 = None
                local_school_guess = None
                local_program_guess = None
                local_facts_local: list[tuple[str, str]] = []
                local_money_signal = None
                local_percent_signal = None
                local_has_deadline_signal = "no"
                local_has_exam_signal = "no"
                local_has_acceptance_signal = "no"
                local_has_applications_signal = "no"
                local_has_admitted_signal = "no"
                local_has_enrolled_signal = "no"
                local_has_yield_signal = "no"
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=12000)
                    page.wait_for_timeout(min(args.wait_ms, 300))
                    # Home-tab forcing is only valid for school homepage URLs.
                    # Running this on /admission can navigate away from the target page.
                    if page_type in {"university", "college", "institute", "school"}:
                        activate_home_tab(page)
                        expand_school_summaries(page)
                        # Some generic "Read More" links can shift page state; re-activate Home tab before extraction.
                        activate_home_tab(page)
                    local_status = resp.status if resp else 0
                    local_html = page.content()
                except PlaywrightTimeoutError:
                    local_status = 0
                    local_html = ""
                except Exception:
                    local_status = 0
                    local_html = ""

                if local_status >= 400:
                    local_html = ""

                if local_html:
                    soup = BeautifulSoup(local_html, "lxml")
                    keep_text_only_dom(soup)

                    if soup.title:
                        local_title = normalize_text(soup.title.get_text(" ", strip=True))
                    h1_node = soup.find("h1")
                    if h1_node:
                        local_h1 = normalize_text(h1_node.get_text(" ", strip=True))

                    local_school_guess, local_program_guess = guess_entities(url, local_title, local_h1)
                    if page_type in {"university", "college", "institute", "school"} and is_school_identity_mismatch(url, local_title, local_h1):
                        local_status = 0
                        local_html = ""
                        local_facts_local = []
                    else:
                        full_text = normalize_text(soup.get_text(" ", strip=True))
                        review_like = is_raw_student_review_page(url, local_title, local_h1, full_text)
                        # Some "Read More" controls can shift the page into student-review content.
                        # Treat this as an invalid scrape for school/admission targets and retry once.
                        if page_type in {"university", "college", "institute", "school", "admission"} and review_like:
                            local_status = 0
                            local_html = ""
                            local_facts_local = []
                            return (
                                local_status,
                                local_html,
                                local_title,
                                local_h1,
                                page_type,
                                local_school_guess,
                                local_program_guess,
                                local_facts_local,
                                local_money_signal,
                                local_percent_signal,
                                local_has_deadline_signal,
                                local_has_exam_signal,
                                local_has_acceptance_signal,
                                local_has_applications_signal,
                                local_has_admitted_signal,
                                local_has_enrolled_signal,
                                local_has_yield_signal,
                            )
                        local_page_type = "school_review" if page_type in {"university", "college", "institute", "school"} and review_like else page_type
                        if is_soft_error_page(full_text):
                            local_status = 403
                            local_html = ""
                            local_facts_local = []
                        else:
                            signals = text_signals(full_text[:9000])
                            local_money_signal = signals["money_signal"]
                            local_percent_signal = signals["percent_signal"]
                            local_has_deadline_signal = signals["has_deadline_signal"]
                            local_has_exam_signal = signals["has_exam_signal"]
                            local_has_acceptance_signal = signals["has_acceptance_signal"]
                            local_has_applications_signal = signals["has_applications_signal"]
                            local_has_admitted_signal = signals["has_admitted_signal"]
                            local_has_enrolled_signal = signals["has_enrolled_signal"]
                            local_has_yield_signal = signals["has_yield_signal"]

                            local_facts_local.extend(extract_table_facts(soup, args.max_line_len, page_type=local_page_type))
                            local_facts_local.extend(
                                extract_text_facts(
                                    soup,
                                    min_line_len=args.min_line_len,
                                    max_line_len=args.max_line_len,
                                    max_facts=args.max_facts_per_page,
                                    page_type=local_page_type,
                                )
                            )
                try:
                    page.close()
                except Exception:
                    pass
                return (
                    local_status,
                    local_html,
                    local_title,
                    local_h1,
                    page_type,
                    local_school_guess,
                    local_program_guess,
                    local_facts_local,
                    local_money_signal,
                    local_percent_signal,
                    local_has_deadline_signal,
                    local_has_exam_signal,
                    local_has_acceptance_signal,
                    local_has_applications_signal,
                    local_has_admitted_signal,
                    local_has_enrolled_signal,
                    local_has_yield_signal,
                )
            status_code, html, title, h1, page_type, school_guess, program_guess, local_facts, money_signal, percent_signal, has_deadline_signal, has_exam_signal, has_acceptance_signal, has_applications_signal, has_admitted_signal, has_enrolled_signal, has_yield_signal = scrape_once()
            # If a school page comes back empty or too thin, retry once in a fresh page.
            if page_type in {"university", "college", "institute", "school", "admission"} and (status_code == 0 or len(local_facts) < 3):
                retry_status, retry_html, retry_title, retry_h1, retry_page_type, retry_school_guess, retry_program_guess, retry_facts, money_signal, percent_signal, has_deadline_signal, has_exam_signal, has_acceptance_signal, has_applications_signal, has_admitted_signal, has_enrolled_signal, has_yield_signal = scrape_once()
                if retry_status > 0 or len(retry_facts) > len(local_facts):
                    status_code = retry_status
                    html = retry_html
                    title = retry_title
                    h1 = retry_h1
                    page_type = retry_page_type
                    school_guess = retry_school_guess
                    program_guess = retry_program_guess
                    local_facts = retry_facts

            school_id = school_id_from(
                url,
                country,
                school_guess,
                program_guess if page_type in {"university", "college", "institute", "school"} else None,
                h1 if page_type in {"university", "college", "institute", "school"} else None,
            )

            # de-duplicate facts per page while preserving order
            deduped: list[tuple[str, str]] = []
            seen = set()
            for k, v in local_facts:
                key = (k, v.lower())
                if key in seen:
                    continue
                seen.add(key)
                deduped.append((k, v))
            local_facts = deduped[: args.max_facts_per_page]

            page_rows.append(
                {
                    "url": url,
                    "school_id": school_id,
                    "status_code": status_code,
                    "page_type": page_type,
                    "country": country,
                    "school_name_guess": school_guess,
                    "program_name_guess": program_guess,
                    "title": title,
                    "h1": h1,
                    "money_signal": money_signal,
                    "percent_signal": percent_signal,
                    "has_deadline_signal": has_deadline_signal,
                    "has_exam_signal": has_exam_signal,
                    "has_acceptance_signal": has_acceptance_signal,
                    "has_applications_signal": has_applications_signal,
                    "has_admitted_signal": has_admitted_signal,
                    "has_enrolled_signal": has_enrolled_signal,
                    "has_yield_signal": has_yield_signal,
                    "fact_count": len(local_facts),
                    "scraped_at": scraped_at,
                }
            )

            for fact_key, fact_value in local_facts:
                fact_rows.append(
                    {
                        "url": url,
                        "school_id": school_id,
                        "page_type": page_type,
                        "country": country,
                        "school_name_guess": school_guess,
                        "program_name_guess": program_guess,
                        "fact_key": fact_key,
                        "fact_value": fact_value,
                        "scraped_at": scraped_at,
                    }
                )

            if i % 200 == 0:
                print(f"processed={i} pages={len(page_rows)} facts={len(fact_rows)}")

            try:
                page.close()
            except Exception:
                pass

        context.close()
        browser.close()

    school_num_id_by_school_id = assign_school_num_ids(page_rows)
    for row in page_rows:
        row["school_num_id"] = school_num_id_by_school_id.get(row.get("school_id") or "unknown")
    for row in fact_rows:
        row["school_num_id"] = school_num_id_by_school_id.get(row.get("school_id") or "unknown")

    write_pages_csv(args.pages_csv, page_rows)
    write_facts_csv(args.facts_csv, fact_rows)

    print(f"pages={len(page_rows)}")
    print(f"facts={len(fact_rows)}")
    print(f"pages_csv={args.pages_csv}")
    print(f"facts_csv={args.facts_csv}")


if __name__ == "__main__":
    main()
