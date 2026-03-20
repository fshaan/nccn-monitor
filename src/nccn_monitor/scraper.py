"""Scrape NCCN guideline category pages for complete version tracking."""

import re
import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# All 4 NCCN professional guideline category pages
CATEGORY_URLS = {
    "Cancer by Type": "https://www.nccn.org/guidelines/category_1",
    "Detection, Prevention & Risk Reduction": "https://www.nccn.org/guidelines/category_2",
    "Supportive Care": "https://www.nccn.org/guidelines/category_3",
    "Specific Populations": "https://www.nccn.org/guidelines/category_4",
}

# Version pattern: "Version X.YYYY" or "Version: X.YYYY"
VERSION_PATTERN = re.compile(r"Version:?\s+(\d+\.\d{4})")

NCCN_BASE = "https://www.nccn.org"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class GuidelineInfo:
    """A single guideline's current version info from NCCN."""

    name: str
    version: str
    detail_url: str  # Link to guideline detail page
    category: str = ""


async def fetch_all_guidelines() -> list[GuidelineInfo]:
    """Fetch ALL NCCN professional guidelines from the 4 category pages.

    This gives us the complete list of 92 guidelines (as of 2026-03),
    unlike the Recently Published page which only shows ~30 recent updates.

    Returns a list of GuidelineInfo with name, version, and detail_url.
    Raises ScrapeError if any category page cannot be fetched or parsed.
    """
    all_guidelines: list[GuidelineInfo] = []

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        for category_name, url in CATEGORY_URLS.items():
            resp = await client.get(url, timeout=30)
            resp.raise_for_status()

            guidelines = parse_category_page(resp.text, category_name)
            all_guidelines.extend(guidelines)
            logger.info("Category '%s': %d guidelines", category_name, len(guidelines))

            # Small delay between requests to be polite
            await asyncio.sleep(1)

    if not all_guidelines:
        raise ScrapeError("No guidelines found across any category page")

    logger.info("Total: %d guidelines across %d categories",
                len(all_guidelines), len(CATEGORY_URLS))
    return all_guidelines


def parse_category_page(html: str, category_name: str) -> list[GuidelineInfo]:
    """Parse a NCCN category page into GuidelineInfo list.

    The page structure (as of 2026-03):
      <div class="row guideline-items">
        <div class="col-md-6">
          <div class="item">
            <div class="item-name">
              <a href="/guidelines/guidelines-detail?category=1&id=1234">
                Guideline Name
              </a>
            </div>
            <div class="item-version">
              Version: X.YYYY
            </div>
          </div>
          ...
        </div>
      </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[GuidelineInfo] = []

    # Find all guideline items
    items = soup.find_all("div", class_="item")

    for item in items:
        # Extract name from item-name > a
        name_div = item.find("div", class_="item-name")
        if not name_div:
            continue

        link = name_div.find("a", href=True)
        if not link:
            continue

        name = link.get_text(strip=True)
        if not name:
            continue

        # Extract version from item-version
        version_div = item.find("div", class_="item-version")
        version = ""
        if version_div:
            version_text = version_div.get_text()
            match = VERSION_PATTERN.search(version_text)
            if match:
                version = match.group(1)

        # Build absolute detail URL
        href = link["href"]
        detail_url = href if href.startswith("http") else NCCN_BASE + href

        results.append(
            GuidelineInfo(
                name=name,
                version=version,
                detail_url=detail_url,
                category=category_name,
            )
        )

    if not results:
        raise ScrapeError(
            f"No guidelines found on category page '{category_name}'. "
            f"The HTML structure may have changed."
        )

    return results


# ── Legacy: Recently Published page (kept for reference) ─────────

RECENTLY_PUBLISHED_URL = "https://www.nccn.org/guidelines/recently-published-guidelines"


async def fetch_recently_published() -> list[GuidelineInfo]:
    """Fetch the Recently Published page (only shows recent updates, not all).

    Kept as a secondary data source. For complete monitoring,
    use fetch_all_guidelines() instead.
    """
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        resp = await client.get(RECENTLY_PUBLISHED_URL, timeout=30)
        resp.raise_for_status()

    return parse_recently_published(resp.text)


def parse_recently_published(html: str) -> list[GuidelineInfo]:
    """Parse the Recently Published page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[GuidelineInfo] = []
    current_category = ""

    content = soup.find("div", class_="content") or soup.find("main") or soup.body
    if not content:
        raise ScrapeError("Cannot find main content area on the page")

    for element in content.descendants:
        if element.name in ("h2", "h3"):
            current_category = element.get_text(strip=True)
            continue

        if element.name == "li":
            link = element.find("a", href=True)
            if not link:
                continue

            href = link["href"]
            if ".pdf" not in href:
                continue

            name = link.get_text(strip=True)
            if not name:
                continue

            li_text = element.get_text()
            version_match = VERSION_PATTERN.search(li_text)
            version = version_match.group(1) if version_match else ""

            pdf_url = href if href.startswith("http") else NCCN_BASE + href

            results.append(
                GuidelineInfo(
                    name=name,
                    version=version,
                    detail_url=pdf_url,
                    category=current_category,
                )
            )

    if not results:
        raise ScrapeError("No guidelines found on Recently Published page")

    return results


class ScrapeError(Exception):
    """Raised when scraping fails due to network or structural issues."""
