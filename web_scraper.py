#!/usr/bin/env python3
"""
Web scraper using requests + BeautifulSoup.
Supports scraping links, images, headings, tables, and custom CSS selectors.

Usage:
    python web_scraper.py --url https://example.com --mode links
    python web_scraper.py --url https://example.com --mode table --output results.json
    python web_scraper.py --url https://example.com --mode selector --selector "article h2"
"""

import argparse
import json
import csv
import time
import logging
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit(
        "Missing dependencies. Install them with:\n"
        "  pip install requests beautifulsoup4"
    )

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PythonScraper/1.0; "
        "+https://github.com/example/scraper)"
    )
}


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class ScrapeResult:
    url: str
    mode: str
    data: list = field(default_factory=list)
    error: Optional[str] = None


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def fetch(url: str, timeout: int = 15, retries: int = 3) -> requests.Response:
    """Fetch a URL with retries and exponential back-off."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            log.warning("Attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


def get_soup(url: str) -> BeautifulSoup:
    resp = fetch(url)
    return BeautifulSoup(resp.text, "html.parser")


# ── Scraping modes ───────────────────────────────────────────────────────────

def scrape_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract all hyperlinks with resolved absolute URLs."""
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.startswith(("javascript:", "mailto:", "#")):
            continue
        absolute = urljoin(base_url, href)
        links.append({
            "text": tag.get_text(strip=True) or "(no text)",
            "url": absolute,
            "domain": urlparse(absolute).netloc,
        })
    return links


def scrape_images(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Extract all images with src, alt text, and dimensions if present."""
    images = []
    for tag in soup.find_all("img"):
        src = tag.get("src", "").strip()
        if not src:
            continue
        images.append({
            "src": urljoin(base_url, src),
            "alt": tag.get("alt", ""),
            "width": tag.get("width", ""),
            "height": tag.get("height", ""),
        })
    return images


def scrape_headings(soup: BeautifulSoup) -> list[dict]:
    """Extract h1–h6 headings in document order."""
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        headings.append({
            "level": tag.name,
            "text": tag.get_text(strip=True),
        })
    return headings


def scrape_tables(soup: BeautifulSoup) -> list[dict]:
    """Extract all HTML tables as lists of row dicts."""
    results = []
    for i, table in enumerate(soup.find_all("table"), start=1):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if not cells:
                continue
            if headers:
                row = dict(zip(headers, cells))
            else:
                row = {f"col_{j}": v for j, v in enumerate(cells)}
            rows.append(row)
        results.append({"table_index": i, "headers": headers, "rows": rows})
    return results


def scrape_selector(soup: BeautifulSoup, selector: str) -> list[dict]:
    """Extract text and HTML of elements matching a CSS selector."""
    return [
        {"text": el.get_text(strip=True), "html": str(el)[:300]}
        for el in soup.select(selector)
    ]


def scrape_metadata(soup: BeautifulSoup, url: str) -> list[dict]:
    """Extract page title, description, and Open Graph / Twitter meta tags."""
    data = {
        "url": url,
        "title": soup.title.string.strip() if soup.title else "",
        "description": "",
        "og": {},
        "twitter": {},
    }
    for meta in soup.find_all("meta"):
        name = meta.get("name", "").lower()
        prop = meta.get("property", "").lower()
        content = meta.get("content", "")
        if name == "description":
            data["description"] = content
        elif prop.startswith("og:"):
            data["og"][prop[3:]] = content
        elif name.startswith("twitter:"):
            data["twitter"][name[8:]] = content
    return [data]


# ── Output writers ───────────────────────────────────────────────────────────

def write_output(result: ScrapeResult, output_path: Optional[str], fmt: str) -> None:
    if result.error:
        log.error("Scrape error: %s", result.error)
        return

    if not output_path:
        print(json.dumps(result.data, indent=2, ensure_ascii=False))
        return

    if fmt == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.data, f, indent=2, ensure_ascii=False)
    elif fmt == "csv":
        if not result.data:
            log.warning("No data to write.")
            return
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=result.data[0].keys())
            writer.writeheader()
            writer.writerows(result.data)
    elif fmt == "txt":
        with open(output_path, "w", encoding="utf-8") as f:
            for item in result.data:
                f.write(str(item) + "\n")

    log.info("Saved %d items → %s (%s)", len(result.data), output_path, fmt)


# ── Main ─────────────────────────────────────────────────────────────────────

MODES = {
    "links":    scrape_links,
    "images":   scrape_images,
    "headings": scrape_headings,
    "tables":   scrape_tables,
    "metadata": scrape_metadata,
    "selector": None,  # handled separately (needs extra arg)
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape a webpage for links, images, headings, tables, or any CSS selector."
    )
    parser.add_argument("--url", required=True, help="Target URL to scrape")
    parser.add_argument(
        "--mode",
        choices=list(MODES),
        default="links",
        help="What to scrape (default: links)",
    )
    parser.add_argument(
        "--selector",
        help="CSS selector — required when --mode=selector",
    )
    parser.add_argument("--output", help="Output file path (default: stdout)")
    parser.add_argument(
        "--format",
        choices=["json", "csv", "txt"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Seconds to wait before fetching (be polite to servers)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.mode == "selector" and not args.selector:
        sys.exit("--selector is required when --mode=selector")

    if args.delay:
        log.info("Waiting %.1fs before fetching…", args.delay)
        time.sleep(args.delay)

    log.info("Fetching %s", args.url)
    result = ScrapeResult(url=args.url, mode=args.mode)

    try:
        soup = get_soup(args.url)

        if args.mode == "links":
            result.data = scrape_links(soup, args.url)
        elif args.mode == "images":
            result.data = scrape_images(soup, args.url)
        elif args.mode == "headings":
            result.data = scrape_headings(soup)
        elif args.mode == "tables":
            result.data = scrape_tables(soup)
        elif args.mode == "metadata":
            result.data = scrape_metadata(soup, args.url)
        elif args.mode == "selector":
            result.data = scrape_selector(soup, args.selector)

        log.info("Found %d item(s)", len(result.data))

    except RuntimeError as exc:
        result.error = str(exc)

    write_output(result, args.output, args.format)


if __name__ == "__main__":
    main()
