"""NCCN login and PDF download — adapted from gscfwid/NCCN_guidelines_MCP."""

import asyncio
import os
import logging
from datetime import datetime
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

PDF_CACHE_MAX_AGE_DAYS = 7

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


class NCCNDownloader:
    """Async downloader that handles NCCN login and PDF caching."""

    def __init__(self, username: str | None = None, password: str | None = None):
        self.username = username
        self.password = password
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=BROWSER_HEADERS, follow_redirects=True, timeout=60
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def login(self, target_url: str) -> bool:
        """Log into NCCN by submitting the login form with hidden fields.

        The flow:
        1. GET target_url → NCCN redirects to login page
        2. Parse login form, extract hidden fields (CSRF token etc.)
        3. POST credentials to /login/Index/
        4. Follow redirects back to target
        """
        if not self.username or not self.password:
            logger.error("Cannot login: no credentials configured")
            return False

        client = await self._get_client()
        try:
            # Step 1: Access target to get redirected to login page
            resp = await client.get(target_url)
            if resp.status_code != 200:
                logger.error("Failed to reach login page: status %d", resp.status_code)
                return False

            # Step 2: Parse login form
            soup = BeautifulSoup(resp.text, "html.parser")
            form = soup.find("form", {"action": "/login/Index/"})
            if not form:
                logger.error("Login form not found on page")
                return False

            form_data = {}
            for inp in form.find_all("input", {"type": "hidden"}):
                name = inp.get("name")
                if name:
                    form_data[name] = inp.get("value", "")

            form_data["Username"] = self.username
            form_data["Password"] = self.password
            form_data["RememberMe"] = "false"

            # Step 3: Submit login
            result = await client.post(
                "https://www.nccn.org/login/Index/",
                data=form_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": str(resp.url),
                    "Origin": "https://www.nccn.org",
                },
            )

            # Step 4: Check success
            if "/login" in str(result.url) or "Log in" in result.text:
                logger.error("Login failed: bad credentials or NCCN form changed")
                return False

            logger.info("NCCN login successful")
            return True

        except Exception as e:
            logger.error("Login error: %s", e)
            return False

    async def download_pdf(
        self,
        pdf_url: str,
        cache_dir: str | Path,
        max_age_days: int = PDF_CACHE_MAX_AGE_DAYS,
    ) -> Path | None:
        """Download a PDF, using cache and auto-login if needed.

        Returns the local file path on success, None on failure.
        """
        cache_path = Path(cache_dir).expanduser()
        cache_path.mkdir(parents=True, exist_ok=True)

        filename = os.path.basename(pdf_url) or "guideline.pdf"
        local_path = cache_path / filename

        # Check cache
        if local_path.exists() and local_path.stat().st_size > 0:
            age_days = (datetime.now() - datetime.fromtimestamp(local_path.stat().st_mtime)).days
            if age_days < max_age_days:
                logger.info("Using cached PDF: %s (%d days old)", filename, age_days)
                return local_path
            logger.info("Cache expired for %s (%d days), re-downloading", filename, age_days)

        client = await self._get_client()
        try:
            resp = await client.get(
                pdf_url, headers={"Accept": "application/pdf,*/*", "Referer": "https://www.nccn.org/"}
            )

            content_type = resp.headers.get("Content-Type", "")

            if "application/pdf" in content_type:
                local_path.write_bytes(resp.content)
                logger.info("Downloaded PDF: %s (%d bytes)", filename, len(resp.content))
                return local_path

            # Got HTML instead of PDF → need to login
            if "text/html" in content_type and ("login" in resp.text.lower()):
                logger.info("Login required, attempting authentication...")
                if await self.login(pdf_url):
                    await asyncio.sleep(1)  # Wait for session to stabilize
                    return await self.download_pdf(pdf_url, cache_dir, max_age_days)
                logger.error("Auto-login failed for %s", pdf_url)
                return None

            logger.error("Unexpected response for %s: content-type=%s", pdf_url, content_type)
            return None

        except Exception as e:
            logger.error("Download error for %s: %s", pdf_url, e)
            return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
