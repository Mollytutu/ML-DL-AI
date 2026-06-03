import argparse
import re
import subprocess
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

TARGET_HINTS = (
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

DEFAULT_SEEDS = [
    "https://collegedunia.com/",
    "https://collegedunia.com/usa",
    "https://collegedunia.com/canada",
    "https://collegedunia.com/uk",
    "https://collegedunia.com/australia",
    "https://collegedunia.com/germany",
    "https://collegedunia.com/ireland",
    "https://collegedunia.com/hong-kong",
    "https://collegedunia.com/malaysia",
    "https://collegedunia.com/netherlands",
    "https://collegedunia.com/new-zealand",
    "https://collegedunia.com/singapore",
    "https://collegedunia.com/sweden",
    "https://collegedunia.com/france",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Discover Collegedunia target links using Selenium BFS")
    p.add_argument("--out", required=True)
    p.add_argument("--seed-file")
    p.add_argument("--max-urls", type=int, default=30000)
    p.add_argument("--max-pages", type=int, default=8000)
    p.add_argument("--max-depth", type=int, default=4)
    p.add_argument("--wait-sec", type=float, default=2.0)
    p.add_argument("--sleep", type=float, default=0.12)
    p.add_argument("--scroll-rounds", type=int, default=4, help="How many times to scroll to the bottom before extracting links.")
    p.add_argument("--scroll-pause", type=float, default=0.35, help="Pause between scroll rounds.")
    p.add_argument("--browser-binary", default=None)
    p.add_argument("--driver-path", default=None)
    p.add_argument("--headless", action="store_true", default=True)
    p.add_argument("--no-headless", dest="headless", action="store_false")
    return p.parse_args()


def load_seeds(seed_file: str | None) -> list[str]:
    if not seed_file:
        return list(DEFAULT_SEEDS)
    lines = Path(seed_file).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def auto_browser_binary(browser_binary: str | None) -> str | None:
    if browser_binary:
        return browser_binary
    for candidate in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/opt/homebrew/bin/google-chrome",
        "/usr/bin/google-chrome",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def normalize_url(base: str, href: str | None) -> str | None:
    if not href:
        return None
    url = urljoin(base, href)
    url, _ = urldefrag(url)
    p = urlparse(url)
    if p.scheme not in {"http", "https"}:
        return None
    host = (p.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "collegedunia.com":
        return None
    if any(ext in url.lower() for ext in (".jpg", ".png", ".webp", ".pdf", ".zip", ".mp4", ".mov")):
        return None
    return url


SCHOOL_HOME_RE = re.compile(
    r"^/(?P<country>[a-z-]+)/(?:university|college|institute|school)/(?P<school_id>\d+-[^/?#]+)(?:/.*)?/?$",
    re.I,
)


def school_homepage_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    match = SCHOOL_HOME_RE.match(parsed.path)
    if not match:
        return None
    country = match.group("country").lower()
    kind = parsed.path.strip("/").split("/")[1]
    school_id = match.group("school_id")
    return f"https://collegedunia.com/{country}/{kind}/{school_id}"


def is_target(url: str) -> bool:
    u = url.lower()
    return any(h in u for h in TARGET_HINTS) or school_homepage_from_url(url) is not None


def should_expand(url: str) -> bool:
    u = url.lower()
    return (
        "/university/" in u
        or "/college/" in u
        or "/institute/" in u
        or "/school/" in u
        or "/course/" in u
        or "/programs/" in u
        or "/page-" in u
        or u.count("/") <= 4
        or any(
            x in u
            for x in [
                "/uk",
                "/canada",
                "/australia",
                "/usa",
                "/ireland",
                "/germany",
                "/new-zealand",
                "/singapore",
                "/netherlands",
                "/switzerland",
                "/france",
                "/italy",
                "/japan",
                "/hong-kong",
                "/uae",
                "/spain",
                "/malaysia",
                "/south-africa",
                "english-lang-universities",
                "the-ranked-universities",
                "bachelor-universities",
                "universities",
                "/college",
            ]
        )
    )


def make_driver(headless: bool, browser_binary: str | None = None, driver_path: str | None = None) -> webdriver.Chrome:
    opts = uc.ChromeOptions()
    browser_binary = auto_browser_binary(browser_binary)
    if headless:
        opts.add_argument("--headless=new")
    if browser_binary:
        opts.binary_location = browser_binary
    # Prefer a fuller load for guarded pages that initially return a short challenge.
    opts.page_load_strategy = "eager"
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1440,2200")
    opts.add_argument("--lang=en-US,en;q=0.9")
    opts.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    opts.add_argument("--disable-blink-features=AutomationControlled")

    version_main = None
    if browser_binary:
        try:
            raw = subprocess.check_output([browser_binary, "--version"], text=True).strip()
            m = re.search(r"(\d+)\.", raw)
            if m:
                version_main = int(m.group(1))
            else:
                version_main = 146
        except Exception:
            version_main = 146

    if driver_path:
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=opts)
    else:
        if version_main:
            driver = uc.Chrome(options=opts, version_main=version_main)
        else:
            driver = uc.Chrome(options=opts)

    driver.set_page_load_timeout(30)
    return driver


def collect_html_with_scroll(driver: webdriver.Chrome, wait_sec: float, scroll_rounds: int, scroll_pause: float) -> str:
    html = ""
    try:
        html = driver.page_source or ""
    except Exception:
        html = ""

    for _ in range(max(0, scroll_rounds)):
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass
        time.sleep(scroll_pause)
        try:
            WebDriverWait(driver, max(wait_sec, 1.0)).until(
                lambda d: d.execute_script("return document.readyState") in {"interactive", "complete"}
            )
        except Exception:
            pass
        try:
            new_html = driver.page_source or ""
            if len(new_html) > len(html):
                html = new_html
        except Exception:
            pass

    return html


def is_challenge_or_block_page(html: str) -> bool:
    lowered = (html or "").lower()
    return (
        "request blocked" in lowered
        or "403 error" in lowered
        or "generated by cloudfront" in lowered
        or "captcha" in lowered
    )


def main() -> None:
    args = parse_args()
    seed_urls = load_seeds(args.seed_file)

    q: deque[tuple[str, int]] = deque((u, 0) for u in seed_urls)
    seen_pages: set[str] = set()
    target_urls: set[str] = set()

    driver = make_driver(args.headless, browser_binary=args.browser_binary, driver_path=args.driver_path)

    try:
        while q and len(seen_pages) < args.max_pages and len(target_urls) < args.max_urls:
            url, depth = q.popleft()
            if url in seen_pages:
                continue
            seen_pages.add(url)

            try:
                try:
                    driver.get(url)
                except Exception:
                    pass
                time.sleep(args.wait_sec)
                WebDriverWait(driver, max(args.wait_sec, 1.0)).until(
                    lambda d: d.execute_script("return document.readyState") in {"interactive", "complete"}
                )
                html = collect_html_with_scroll(driver, args.wait_sec, args.scroll_rounds, args.scroll_pause)
                if len(html) < 5000 or is_challenge_or_block_page(html):
                    # Retry once after a short pause if we only got a challenge shell.
                    time.sleep(max(1.0, args.wait_sec))
                    try:
                        driver.refresh()
                    except Exception:
                        try:
                            driver.get(url)
                        except Exception:
                            pass
                    time.sleep(max(1.0, args.wait_sec))
                    html_retry = collect_html_with_scroll(driver, args.wait_sec, args.scroll_rounds + 2, args.scroll_pause)
                    if len(html_retry) > len(html):
                        html = html_retry
            except Exception:
                continue

            soup = BeautifulSoup(html, "lxml")
            links = []
            for a in soup.select("a[href]"):
                nu = normalize_url(url, a.get("href"))
                if nu:
                    links.append(nu)

            for nu in links:
                school_home = school_homepage_from_url(nu)
                if school_home:
                    target_urls.add(school_home)
                elif is_target(nu):
                    target_urls.add(nu)
                    if len(target_urls) >= args.max_urls:
                        break
                if depth < args.max_depth and should_expand(nu) and nu not in seen_pages:
                    q.append((nu, depth + 1))

            if len(seen_pages) % 100 == 0:
                print(f"progress pages={len(seen_pages)} queue={len(q)} targets={len(target_urls)}")

            time.sleep(args.sleep)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    ordered = sorted(target_urls)
    with open(args.out, "w", encoding="utf-8") as f:
        for u in ordered:
            f.write(u + "\n")

    print(f"pages_scanned={len(seen_pages)}")
    print(f"urls_saved={len(ordered)}")
    print(f"out={args.out}")


if __name__ == "__main__":
    main()
