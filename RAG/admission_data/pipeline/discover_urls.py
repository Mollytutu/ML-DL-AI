import argparse
import re
import time
from collections import deque
from xml.etree import ElementTree as ET

import requests

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
INCLUDE_HINTS = (
    "/university/",
    "/college/",
    "/institute/",
    "/school/",
    "/course/",
    "/programs/",
    "/admission",
    "/fees",
    "/ranking",
    "-universities",
    "-colleges",
    "/page-",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover Collegedunia URLs from sitemap graph")
    parser.add_argument("--start-sitemap", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-sitemaps", type=int, default=2000)
    parser.add_argument("--max-urls", type=int, default=20000)
    parser.add_argument("--sleep", type=float, default=0.1)
    return parser.parse_args()


def fetch_text(session: requests.Session, url: str) -> str | None:
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code >= 400:
            return None
        return resp.text
    except requests.RequestException:
        return None


def extract_nodes(xml_text: str) -> tuple[list[str], list[str]]:
    sitemap_urls: list[str] = []
    page_urls: list[str] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return sitemap_urls, page_urls

    tag = root.tag.lower()
    if tag.endswith("sitemapindex"):
        for node in root.findall("sm:sitemap/sm:loc", NS):
            if node.text:
                sitemap_urls.append(node.text.strip())
    elif tag.endswith("urlset"):
        for node in root.findall("sm:url/sm:loc", NS):
            if node.text:
                page_urls.append(node.text.strip())
    return sitemap_urls, page_urls


def is_useful_url(url: str) -> bool:
    u = url.lower()
    if not u.startswith("https://collegedunia.com"):
        return False
    if any(ext in u for ext in (".jpg", ".png", ".webp", ".pdf", ".zip")):
        return False
    return any(h in u for h in INCLUDE_HINTS)


def main() -> None:
    args = parse_args()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; admission_data_bot/1.0)"})

    q: deque[str] = deque([args.start_sitemap])
    seen_sitemaps: set[str] = set()
    out_urls: set[str] = set()

    while q and len(seen_sitemaps) < args.max_sitemaps and len(out_urls) < args.max_urls:
        sm = q.popleft()
        if sm in seen_sitemaps:
            continue
        seen_sitemaps.add(sm)

        xml_text = fetch_text(session, sm)
        if not xml_text:
            continue

        sitemaps, pages = extract_nodes(xml_text)
        for nxt in sitemaps:
            if nxt not in seen_sitemaps:
                q.append(nxt)

        for url in pages:
            if is_useful_url(url):
                out_urls.add(url)
                if len(out_urls) >= args.max_urls:
                    break

        time.sleep(args.sleep)

    ordered = sorted(out_urls)
    with open(args.out, "w", encoding="utf-8") as f:
        for url in ordered:
            f.write(url + "\n")

    print(f"sitemaps_scanned={len(seen_sitemaps)}")
    print(f"urls_saved={len(ordered)}")
    print(f"out={args.out}")


if __name__ == "__main__":
    main()
