from __future__ import annotations

import re


_DANGEROUS_PREFIXES = ("=", "+", "-", "@")
_LOCAL_CURRENCY_MONEY_RE = re.compile(
    r"(USD|AUD|CAD|EUR|GBP|AED|HKD|MYR|NZD|SEK|\$|£|€)\s?[0-9][0-9,]*(?:\.[0-9]+)?",
    re.I,
)
_INR_CURRENCY_TOKEN_RE = re.compile(r"(₹|INR)", re.I)
_INR_PAREN_RE = re.compile(r"\([^()]*?(?:₹|INR)[^()]*?\)")
_INR_MONEY_RE = re.compile(r"(?:₹|INR)\s?[0-9][0-9,]*(?:\.[0-9]+)?(?:\s*[A-Za-z./-]+)?", re.I)
_INDIAN_SCALE_RE = re.compile(r"\b(?:lakh|lakhs|crore|crores)\b", re.I)
_INDIAN_AUDIENCE_PATTERNS = [
    (re.compile(r"\bIndian students\b", re.I), "international students"),
    (re.compile(r"\bIndian student\b", re.I), "international student"),
    (re.compile(r"\bIndian applicants\b", re.I), "international applicants"),
    (re.compile(r"\bIndian applicant\b", re.I), "international applicant"),
    (re.compile(r"\bIndian\b", re.I), "international"),
    (re.compile(r"\bIndia\b", re.I), "international"),
]


def sanitize_cell(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in _DANGEROUS_PREFIXES:
        return "'" + text
    return text


def sanitize_row(row: dict, fieldnames: list[str]) -> dict:
    return {field: sanitize_cell(row.get(field, "")) for field in fieldnames}


def contains_inr_currency(text: str | None) -> bool:
    return bool(text and _INR_CURRENCY_TOKEN_RE.search(text))


def normalize_audience_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = str(text)
    for pattern, replacement in _INDIAN_AUDIENCE_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


def clean_local_currency_text(text: str | None) -> str:
    if not text:
        return ""

    cleaned = str(text)
    has_indian_local_context = contains_inr_currency(cleaned) or bool(_INDIAN_SCALE_RE.search(cleaned))
    if not has_indian_local_context:
        return cleaned

    cleaned = _INR_PAREN_RE.sub("", cleaned)
    cleaned = _INR_MONEY_RE.sub("", cleaned)
    cleaned = _INR_CURRENCY_TOKEN_RE.sub("", cleaned)
    cleaned = _INDIAN_SCALE_RE.sub("", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
    cleaned = cleaned.strip(" ,;|")
    if not cleaned:
        return ""
    if contains_inr_currency(cleaned) or _INDIAN_SCALE_RE.search(cleaned):
        return ""
    if not _LOCAL_CURRENCY_MONEY_RE.search(cleaned):
        return ""
    return cleaned
