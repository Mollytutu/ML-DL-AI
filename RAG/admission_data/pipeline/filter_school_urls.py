import argparse
import re
from pathlib import Path
from urllib.parse import urlparse

SCHOOL_URL_RE = re.compile(
    r"^/(?P<country>[a-z-]+)/(?:university|college|institute|school)/\d+-[^/?#]+(?:/[^?#]+)*/?$",
    re.I,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Filter Collegedunia URLs down to school-level university pages")
    p.add_argument("--in-file", required=True)
    p.add_argument("--out-file", required=True)
    return p.parse_args()


def is_school_url(url: str) -> bool:
    u = url.lower()
    if not u.startswith("https://collegedunia.com/"):
        return False
    parsed = urlparse(url)
    match = SCHOOL_URL_RE.match(parsed.path)
    if not match:
        return False
    country = match.group("country").lower()
    if country == "india":
        return False
    parts = [part.lower() for part in parsed.path.strip("/").split("/") if part]
    if any("review" in part for part in parts):
        return False
    return True


def main() -> None:
    args = parse_args()
    in_path = Path(args.in_file)
    out_path = Path(args.out_file)

    urls = [line.strip() for line in in_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    kept = [u for u in urls if is_school_url(u)]

    out_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    print(f"input={len(urls)}")
    print(f"kept={len(kept)}")
    print(f"out_file={out_path}")


if __name__ == "__main__":
    main()
