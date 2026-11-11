"""Scrape NCCN guideline category pages for complete version tracking."""

import re
import asyncio
import logging
from datetime import datetime
from pathlib import Path

import httpx
import yaml
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


# ── PDF Index: detail page crawling for PDF URLs ─────────────────

PDF_INDEX_MAX_AGE_DAYS = 7
CONCURRENT_LIMIT = 5


def slugify(name: str) -> str:
    """Convert a guideline name to a filesystem-safe slug.

    Examples:
        "Non-Small Cell Lung Cancer" → "non-small-cell-lung-cancer"
        "Melanoma: Uveal" → "melanoma-uveal"
        "Ovarian Cancer/Fallopian Tube Cancer/Primary Peritoneal Cancer"
            → "ovarian-cancer-fallopian-tube-cancer-primary-peritoneal-cancer"
    """
    slug = name.lower()
    slug = re.sub(r"[/:()]+", " ", slug)   # Replace special chars with space
    slug = re.sub(r"[^\w\s-]", "", slug)   # Remove remaining non-alphanumeric
    slug = re.sub(r"[\s_]+", "-", slug)    # Spaces/underscores to hyphens
    slug = slug.strip("-")
    return slug


def format_pdf_filename(name: str, version: str, lang: str = "EN") -> str:
    """Generate standardized PDF filename.

    Format: NCCN_<CamelCase>_<Year>.V<Num>_<Lang>.pdf

    Examples:
        ("Gastric Cancer", "2.2026") → "NCCN_GastricCancer_2026.V2_EN.pdf"
        ("Non-Small Cell Lung Cancer", "5.2026") → "NCCN_NonSmallCellLungCancer_2026.V5_EN.pdf"
        ("Melanoma: Uveal", "2.2026") → "NCCN_MelanomaUveal_2026.V2_EN.pdf"
        ("B-Cell Lymphomas", "3.2026") → "NCCN_BCellLymphomas_2026.V3_EN.pdf"
    """
    # CamelCase: split on spaces, hyphens, and special chars, capitalize each word
    clean = re.sub(r"[/:()]+", " ", name)       # Special chars → space
    clean = re.sub(r"[^\w\s-]", "", clean)      # Remove non-alphanumeric except hyphen
    words = re.split(r"[\s\-]+", clean)          # Split on spaces AND hyphens
    camel = "".join(w.capitalize() for w in words if w)

    # Parse version "X.YYYY" → year=YYYY, num=X
    parts = version.split(".")
    if len(parts) == 2:
        ver_num, year = parts[0], parts[1]
    else:
        ver_num, year = version, "0000"

    return f"NCCN_{camel}_{year}.V{ver_num}_{lang}.pdf"


@dataclass
class PdfIndexEntry:
    """A guideline's PDF URL discovered from its detail page."""

    name: str
    slug: str
    pdf_url: str
    version: str = ""
    detail_url: str = ""
    category: str = ""


async def fetch_pdf_index(
    guidelines: list[GuidelineInfo],
    index_file: str | Path = "~/.nccn-monitor/index.yaml",
) -> list[PdfIndexEntry]:
    """Build a complete name→PDF URL index by crawling detail pages.

    Crawls each guideline's detail page to find the main PDF download link.
    Uses a cached index file (YAML, 7-day TTL) to avoid repeated crawling.

    Args:
        guidelines: List of guidelines from fetch_all_guidelines().
        index_file: Path to the cached index file.

    Returns:
        List of PdfIndexEntry with PDF URLs for all discoverable guidelines.
    """
    path = Path(index_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Check cache
    if path.exists():
        try:
            with open(path) as f:
                cached = yaml.safe_load(f)
            if cached and "created_at" in cached:
                age = (datetime.now() - datetime.fromisoformat(cached["created_at"])).days
                if age < PDF_INDEX_MAX_AGE_DAYS:
                    entries = [PdfIndexEntry(**e) for e in cached.get("entries", [])]
                    logger.info("Using cached PDF index (%d entries, %d days old)", len(entries), age)
                    return entries
                logger.info("PDF index cache expired (%d days), rebuilding", age)
        except Exception as e:
            logger.warning("Could not read PDF index cache: %s", e)

    # Build index by crawling detail pages
    entries = await _crawl_detail_pages(guidelines)

    # Save cache
    cache_data = {
        "created_at": datetime.now().isoformat(),
        "entry_count": len(entries),
        "entries": [
            {
                "name": e.name,
                "slug": e.slug,
                "pdf_url": e.pdf_url,
                "version": e.version,
                "detail_url": e.detail_url,
                "category": e.category,
            }
            for e in entries
        ],
    }
    with open(path, "w") as f:
        yaml.dump(cache_data, f, default_flow_style=False, allow_unicode=True)
    logger.info("PDF index built and cached: %d entries → %s", len(entries), path)

    return entries


async def _crawl_detail_pages(guidelines: list[GuidelineInfo]) -> list[PdfIndexEntry]:
    """Crawl all detail pages concurrently to extract PDF URLs.

    Uses asyncio.Semaphore to limit concurrency to CONCURRENT_LIMIT,
    with a small delay between requests to be polite to NCCN servers.
    """
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    entries: list[PdfIndexEntry] = []

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:

        async def crawl_one(guideline: GuidelineInfo) -> PdfIndexEntry | None:
            async with semaphore:
                try:
                    resp = await client.get(guideline.detail_url)
                    resp.raise_for_status()
                    pdf_url = parse_detail_page_for_pdf(resp.text)
                    if pdf_url:
                        return PdfIndexEntry(
                            name=guideline.name,
                            slug=slugify(guideline.name),
                            pdf_url=pdf_url,
                            version=guideline.version,
                            detail_url=guideline.detail_url,
                            category=guideline.category,
                        )
                    else:
                        logger.warning("No PDF link found on detail page for: %s", guideline.name)
                        return None
                except Exception as e:
                    logger.warning("Failed to crawl detail page for %s: %s", guideline.name, e)
                    return None
                finally:
                    await asyncio.sleep(0.5)  # Rate limit between requests

        tasks = [crawl_one(g) for g in guidelines]
        results = await asyncio.gather(*tasks)

    for r in results:
        if r:
            entries.append(r)

    logger.info("PDF index: %d/%d guidelines have PDF URLs", len(entries), len(guidelines))
    return entries


def parse_detail_page_for_pdf(html: str) -> str | None:
    """Extract the main guideline PDF URL from a detail page.

    The detail page structure (as of 2026-03):
      <h4 class="GL">Guidelines</h4>
      <ul class="pdfList">
        <li><p><a href="/professionals/physician_gls/pdf/xxx.pdf">NCCN Guidelines</a>
            <span> Version X.YYYY</span></p></li>
      </ul>

    Returns the absolute PDF URL, or None if not found.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Strategy 1: Find <h4 class="GL"> section's PDF list
    gl_header = soup.find("h4", class_="GL")
    if gl_header:
        # Look for the next pdfList after this header
        pdf_list = gl_header.find_next("ul", class_="pdfList")
        if pdf_list:
            hrefs = _pdf_hrefs(pdf_list)
            if hrefs:
                return _select_main_pdf(hrefs)

    # Strategy 2: Fallback — find any professional guideline PDF link
    fallback = [
        href for href in _pdf_hrefs(soup)
        if "/professionals/physician_gls/pdf/" in href and href.endswith(".pdf")
    ]
    return _select_main_pdf(fallback)


def _pdf_hrefs(container) -> list[str]:
    hrefs = []
    for link in container.find_all("a", href=True):
        href = link["href"]
        if href and ".pdf" in href:
            hrefs.append(href)
    return hrefs


def _is_patient_pdf(href: str) -> bool:
    """Patient-guide URLs and filenames are not the professional guideline."""
    lowered = href.lower()
    filename = lowered.rsplit("/", 1)[-1]
    return "/patients/" in lowered or "patient" in filename


def _is_non_main_professional_pdf(href: str) -> bool:
    """Evidence Blocks and framework variants are not the main guideline."""
    lowered = href.lower()
    return any(marker in lowered for marker in ("_blocks", "_core", "_basic", "_enhanced"))


def _select_main_pdf(hrefs: list[str]) -> str | None:
    for href in hrefs:
        if _is_patient_pdf(href) or _is_non_main_professional_pdf(href):
            continue
        return href if href.startswith("http") else NCCN_BASE + href
    return None


class ScrapeError(Exception):
    """Raised when scraping fails due to network or structural issues."""
