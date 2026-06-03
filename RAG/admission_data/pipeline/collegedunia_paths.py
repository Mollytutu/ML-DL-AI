import re
from dataclasses import dataclass
from urllib.parse import urlparse


HOME_KINDS = {"university", "college", "institute", "school"}

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

PROGRAM_HINT_RE = re.compile(
    r"(bachelor|undergraduate|bs\b|ba\b|bsc\b|beng\b|master|ms\b|msc\b|ma\b|mba\b|phd|doctoral|dphil|"
    r"program|programs|course|courses|certificate|diploma|degree)",
    re.I,
)

SCHOOL_SUBPAGE_HINT_RE = re.compile(
    r"(admission|admissions|fees|tuition|ranking|rankings|scholarship|scholarships|gallery|"
    r"placement|placements|campus|about|overview|contact|eligibility|deadline|requirement|requirements|intake|apply)",
    re.I,
)

DEGREE_HINTS = {
    "phd": re.compile(r"(phd|doctoral|dphil|doctorate)", re.I),
    "master": re.compile(r"(master|postgraduate|post graduate|m\.?s\.?|msc|m\.?a\.?|mba|mcom|m\.?eng|llm)", re.I),
    "bachelor": re.compile(r"(bachelor|undergraduate|undergrad|graduate diploma|b\.?s\.?\b|b\.?a\.?\b|b\.?sc\.?\b|b\.?eng\.?\b)", re.I),
    "diploma": re.compile(r"(diploma)", re.I),
    "certificate": re.compile(r"(certificate)", re.I),
    "associate": re.compile(r"(associate|associates)", re.I),
    "foundation": re.compile(r"(foundation)", re.I),
}


PROGRAM_LEVEL_MAP = {
    "phd": "phd",
    "master": "master",
    "bachelor": "undergrad",
    "diploma": "certificate",
    "certificate": "certificate",
    "associate": "undergrad",
    "foundation": "undergrad",
}


def normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def slugify(text: str | None) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def display_name_from_slug(slug: str | None) -> str:
    text = normalize_text((slug or "").replace("_", " ").replace("-", " "))
    if not text:
        return "Unknown"
    words = []
    for part in text.split():
        if part.lower() in {"usa", "uk", "uae", "mit", "nyu", "ntu", "nus", "ucla"}:
            words.append(part.upper())
        else:
            words.append(part.capitalize())
    return " ".join(words).strip()


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


def country_from_url(url: str | None) -> str | None:
    if not url:
        return None
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    first = path.split("/")[0].lower()
    if first in KNOWN_COUNTRY_SLUGS:
        return first
    if first in HOME_KINDS:
        return "india"
    return None


@dataclass(frozen=True)
class SchoolHomepageParts:
    country: str
    kind: str
    slug: str
    tail: tuple[str, ...]


def school_homepage_parts(url: str | None) -> SchoolHomepageParts | None:
    if not url:
        return None
    path = urlparse(url).path.strip("/")
    parts = [part for part in path.split("/") if part]
    if len(parts) < 3:
        return None
    country, kind, slug = parts[0].lower(), parts[1].lower(), parts[2]
    if kind not in HOME_KINDS:
        return None
    if not re.match(r"^\d+-[^/?#]+$", slug):
        return None
    return SchoolHomepageParts(country=country, kind=kind, slug=slug, tail=tuple(parts[3:]))


def school_homepage_from_url(url: str | None) -> str | None:
    parts = school_homepage_parts(url)
    if not parts:
        return None
    return f"https://collegedunia.com/{parts.country}/{parts.kind}/{parts.slug}"


def is_review_url(url: str | None) -> bool:
    if not url:
        return False
    path = urlparse(url).path.strip("/").lower()
    if not path:
        return False
    return bool(re.search(r"(^|/)(reviews?|ratings?)(/|$)", path) or "review-and-ratings" in path)


def school_slug_from_url(url: str | None) -> str:
    parts = school_homepage_parts(url)
    if parts:
        slug = re.sub(r"^\d+-", "", parts.slug)
        return slug or "unknown_school"
    if not url:
        return "unknown_school"
    path = urlparse(url).path.strip("/")
    if not path:
        return "unknown_school"
    slug = path.split("/")[-1]
    slug = re.sub(r"^\d+-", "", slug)
    slug = re.sub(r"-(admissions?|fees?|rankings?|scholarships?|courses?|programs?)\b.*$", "", slug, flags=re.I)
    slug = re.sub(r"-(admissions?|fees?|rankings?|scholarships?|courses?|programs?)$", "", slug, flags=re.I)
    return slug or "unknown_school"


def program_slug_from_url(url: str | None) -> str:
    if not url:
        return "unknown_program"
    path = urlparse(url).path.strip("/")
    if not path:
        return "unknown_program"
    slug = path.split("/")[-1]
    slug = re.sub(r"^\d+-", "", slug)
    slug = re.sub(r"[?#].*$", "", slug)
    if slug.lower() in {"program", "programs", "courses", "course"}:
        return "unknown_program"
    return slug or "unknown_program"


def is_generic_program_index_url(url: str | None) -> bool:
    if not url:
        return False
    path = urlparse(url).path.strip("/").lower()
    if not path:
        return False
    last = path.split("/")[-1]
    return last in {"program", "programs", "course", "courses"}


def page_role_from_url(url: str | None) -> str:
    if is_review_url(url):
        return "other"
    parts = school_homepage_parts(url)
    if not parts:
        return "other"
    if not parts.tail:
        return "school_homepage"

    tail_text = "/".join(parts.tail).lower()
    if "/course/" in tail_text or "/programs/" in tail_text or PROGRAM_HINT_RE.search(tail_text):
        return "program"
    if re.search(r"(^|/)(admission|admissions)(/|$)", tail_text):
        return "admission"
    if SCHOOL_SUBPAGE_HINT_RE.search(tail_text):
        return "school_subpage"
    return "school_subpage"


def infer_school_name_from_row(row: dict, fallback_url: str | None = None) -> str | None:
    for candidate in (
        row.get("school_name_guess"),
        row.get("h1"),
        row.get("title"),
    ):
        text = normalize_text(candidate)
        if not text:
            continue
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

    slug = school_slug_from_url(fallback_url or row.get("url"))
    return display_name_from_slug(slug) if slug else None


def infer_program_name_from_row(row: dict, fallback_url: str | None = None) -> str | None:
    url = fallback_url or row.get("url")
    for candidate in (
        row.get("program_name_guess"),
        row.get("h1"),
        row.get("title"),
    ):
        text = normalize_text(candidate)
        if not text:
            continue
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

    if is_generic_program_index_url(url):
        return "Programs"

    slug = program_slug_from_url(url)
    if slug and slug != "unknown_program":
        text = display_name_from_slug(slug)
        if text and text.lower() not in {"program", "programs", "course", "courses"}:
            return text

    slug = school_slug_from_url(url)
    return display_name_from_slug(slug) if slug else None


def infer_degree_level(text: str | None) -> str | None:
    t = normalize_text(text).lower()
    if not t:
        return None
    for label, rx in DEGREE_HINTS.items():
        if rx.search(t):
            return label
    return None


def normalize_program_level(degree_level: str | None) -> str:
    level = normalize_text(degree_level).lower()
    if not level:
        return "other"
    return PROGRAM_LEVEL_MAP.get(level, "other")


def infer_school_id_from_row(row: dict, fallback_url: str | None = None) -> str:
    existing = normalize_text(row.get("school_id"))
    if existing and existing != "unknown":
        return existing
    country = slugify(row.get("country") or country_from_url(row.get("url") or fallback_url) or "unknown")
    base = infer_school_name_from_row(row, fallback_url=fallback_url)
    if not base:
        base = display_name_from_slug(school_slug_from_url(fallback_url or row.get("url")))
    return f"{country}_{slugify(base)}"


def infer_program_id(school_id: str, row: dict, fallback_url: str | None = None) -> str:
    program_name = infer_program_name_from_row(row, fallback_url=fallback_url)
    if not program_name:
        program_name = display_name_from_slug(school_slug_from_url(fallback_url or row.get("url")))
    return f"{school_id}__{slugify(program_name)}"
