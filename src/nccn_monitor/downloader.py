"""NCCN login and PDF download + version archiving."""

import asyncio
import json
import os
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

PDF_CACHE_MAX_AGE_DAYS = 7
# Positive identity of an NCCN professional guideline. A cover may also mention
# the patient series; that cross-link is not used as a rejection by itself.
PROFESSIONAL_SERIES_MARKER = "clinical practice guidelines in oncology"
_ARCHIVE_TEXT_PAGES = 5

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Accept-Encoding is left to httpx, which advertises only decoders it can read.
    "Connection": "keep-alive",
}


def file_starts_with_pdf(path: Path) -> bool:
    """True when the file begins with the PDF magic header."""
    try:
        with path.open("rb") as handle:
            return handle.read(5).startswith(b"%PDF")
    except OSError:
        return False


def _listable_archive_file(path: Path) -> bool:
    """Files that may appear in archive history. HTML occupants are omitted."""
    return path.is_file() and path.stat().st_size > 0 and not file_is_html_document(path)


def file_is_html_document(path: Path) -> bool:
    """True when the file's leading bytes are an HTML/login document."""
    try:
        with path.open("rb") as handle:
            head = handle.read(64).lstrip()
    except OSError:
        return False
    return head.startswith((b"<", b"\xef\xbb\xbf<"))


def extract_archive_text(path: Path, max_pages: int = _ARCHIVE_TEXT_PAGES) -> str:
    """Extract text from the first pages. Layout coordinates are not used."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return re.sub(r"\s+", " ", "\n".join(parts)).strip()


def professional_pdf_matches(path: Path, name: str, version: str) -> bool:
    """Accept a PDF only with professional identity plus the requested name and version.

    Occurrence of the patient-series phrase is not a rejection. The same text
    checks apply to an existing file and to a newly downloaded one.
    """
    if not file_starts_with_pdf(path) or not name or not version:
        return False
    try:
        text = extract_archive_text(path).casefold()
    except Exception:
        logger.info("Rejected unreadable PDF candidate: %s", path.name)
        return False
    folded_name = re.sub(r"\s+", " ", name).strip().casefold()
    return (
        PROFESSIONAL_SERIES_MARKER in text
        and folded_name in text
        and version.casefold() in text
    )


ARCHIVE_VALID = "valid"
ARCHIVE_MISSING = "missing"
ARCHIVE_BLOCKED_INVALID_EXISTING = "blocked_invalid_existing"
ARCHIVE_REPLACEABLE_NON_PDF = "replaceable_non_pdf"
BLOCKED_EXISTING_PDF_MESSAGE = "blocked-invalid-existing pending manual disposition"


def current_archive_file(
    slug: str,
    version: str,
    name: str,
    archive_dir: str | Path,
    filename: str = "",
) -> Path:
    """Path of the standard file for one recorded version. Older versions are not searched."""
    from .scraper import format_pdf_filename

    if not filename and name:
        filename = format_pdf_filename(name, version)
    elif not filename:
        filename = "guideline.pdf"
    return Path(archive_dir).expanduser() / slug / f"v{version}" / filename


def classify_current_archive(
    slug: str,
    version: str,
    name: str,
    archive_dir: str | Path,
    filename: str = "",
) -> str:
    """Classify the recorded version's standard file.

    ``valid`` passes the same professional name/version text check as a new download.
    ``blocked_invalid_existing`` is an existing ``%PDF`` that fails that check.
    Callers must not delete or overwrite a blocked file.
    ``replaceable_non_pdf`` is a non-PDF occupant such as a login page.
    ``missing`` means there is no non-empty file at the standard path.
    """
    path = current_archive_file(slug, version, name, archive_dir, filename)
    if not path.is_file() or path.stat().st_size <= 0:
        return ARCHIVE_MISSING
    if not file_starts_with_pdf(path):
        return ARCHIVE_REPLACEABLE_NON_PDF
    if professional_pdf_matches(path, name, version):
        return ARCHIVE_VALID
    return ARCHIVE_BLOCKED_INVALID_EXISTING


def valid_current_archive_exists(
    slug: str,
    version: str,
    name: str,
    archive_dir: str | Path,
    filename: str = "",
) -> bool:
    """Whether this recorded version has a matching professional PDF.

    Only that current version is checked. A ``%PDF`` header alone is not enough,
    and older version directories are not scanned.
    """
    return classify_current_archive(slug, version, name, archive_dir, filename) == ARCHIVE_VALID


def archive_followups_for_recorded_versions(
    guidelines,
    known: dict,
    watch_list: list[str] | None,
    archive_dir: str | Path,
    slug_for_name: dict[str, str] | None = None,
    skip_names: set[str] | None = None,
) -> list[dict]:
    """Recorded monitored versions that are not a valid professional archive.

    This is the shared check a weekly caller can use after ``detect_changes``
    returns an empty list. It does not change that empty list, and it does not
    download or modify files. ``blocked_invalid_existing`` items must be left
    for manual disposition. The external weekly wrapper does not call this yet.
    """
    watch_set = {name.lower() for name in watch_list} if watch_list else None
    skipped = skip_names or set()
    slug_for_name = slug_for_name or {}
    followups = []
    for info in guidelines:
        if watch_set is not None and info.name.lower() not in watch_set:
            continue
        if info.name in skipped:
            continue
        recorded = known.get(info.name) or {}
        version = recorded.get("version") or ""
        if not version:
            continue
        slug = slug_for_name.get(info.name)
        if not slug:
            from .scraper import slugify
            slug = slugify(info.name)
        status = classify_current_archive(slug, version, info.name, archive_dir)
        if status == ARCHIVE_VALID:
            continue
        followups.append({
            "name": info.name,
            "version": version,
            "slug": slug,
            "status": status,
            "detail_url": getattr(info, "detail_url", ""),
            "category": getattr(info, "category", ""),
        })
    return followups


_DIAGNOSTIC_MEDIA_TYPES = frozenset({
    "text/html",
    "text/plain",
    "application/pdf",
    "application/xhtml+xml",
})
_NCCN_HOSTS = frozenset({"nccn.org", "www.nccn.org"})


def _media_type(content_type: str) -> str:
    """Return an allowlisted media type, never the raw header."""
    media = content_type.split(";", 1)[0].strip().lower()
    if media in _DIAGNOSTIC_MEDIA_TYPES:
        return media
    return "other" if media else ""


def _host_class(hostname: str | None) -> str:
    if (hostname or "").lower() in _NCCN_HOSTS:
        return "nccn"
    return "other"


def _path_class(path: str) -> str:
    """Classify a path. The path text itself is not returned."""
    normalized = path or "/"
    if len(normalized) > 1 and normalized.endswith("/"):
        trimmed = normalized[:-1]
    else:
        trimmed = normalized
    if trimmed.lower() == "/login/index":
        return "login"
    if trimmed == "/":
        return "known-root"
    return "other"


def _brotli_decoder_present() -> bool:
    try:
        import brotli  # noqa: F401
    except ImportError:
        try:
            import brotlicffi  # noqa: F401
        except ImportError:
            return False
    return True


def _content_encoding_class(response) -> str:
    try:
        values = response.headers.get_list("content-encoding")
    except Exception:
        raw = response.headers.get("content-encoding", "")
        values = [raw] if raw else []
    if not values or not str(values[0]).strip():
        return "absent"
    token = str(values[0]).split(",", 1)[0].strip().lower()
    if token in {"gzip", "deflate", "br"}:
        return token
    return "other"


def _body_decodable(response, encoding_class: str, brotli_present: bool) -> bool:
    if encoding_class == "br" and not brotli_present:
        return False
    if encoding_class == "other":
        return False
    try:
        response.text
    except Exception:
        return False
    return True


def _challenge_class(text: str) -> str:
    folded = re.sub(r"\s+", " ", text or "").casefold()
    if any(marker in folded for marker in (
        "just a moment",
        "cf-challenge",
        "challenge-platform",
        "cdn-cgi/challenge",
    )):
        return "interstitial-marker"
    if any(marker in folded for marker in ("recaptcha", "hcaptcha", "captcha")):
        return "captcha-marker"
    return "none"


def _one_action_class(action) -> str:
    if not isinstance(action, str) or not action.strip():
        return "absent"
    raw = action.strip()
    if raw == "/login/Index/":
        return "exact-relative"
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    path = parts.path or ""
    if path.lower().rstrip("/") == "/login/index":
        return "slash-or-case-variant"
    if host in _NCCN_HOSTS:
        return "absolute-nccn"
    return "other"


def _form_action_class(text: str) -> str:
    soup = BeautifulSoup(text or "", "html.parser")
    forms = soup.find_all("form")
    if not forms:
        return "absent"
    priority = {
        "exact-relative": 0,
        "slash-or-case-variant": 1,
        "absolute-nccn": 2,
        "other": 3,
        "absent": 4,
    }
    best = "absent"
    for form in forms:
        kind = _one_action_class(form.get("action"))
        if priority[kind] < priority[best]:
            best = kind
    return best


def _password_control(text: str) -> str:
    soup = BeautifulSoup(text or "", "html.parser")
    other_type = False
    for inp in soup.find_all("input"):
        typ = inp.get("type")
        name = inp.get("name")
        typ_l = typ.casefold() if isinstance(typ, str) else ""
        name_l = name.casefold() if isinstance(name, str) else ""
        if typ_l == "password":
            return "type-password"
        if name_l == "password":
            other_type = True
    return "other-type" if other_type else "absent"


def _username_control(text: str) -> str:
    soup = BeautifulSoup(text or "", "html.parser")
    for inp in soup.find_all("input"):
        name = inp.get("name")
        if isinstance(name, str) and name.casefold() == "username":
            return "present"
    return "absent"


def _hidden_count_class(text: str) -> str:
    soup = BeautifulSoup(text or "", "html.parser")
    count = 0
    for inp in soup.find_all("input"):
        typ = inp.get("type")
        if isinstance(typ, str) and typ.casefold() == "hidden":
            count += 1
    if count <= 0:
        return "zero"
    if count == 1:
        return "one"
    return "several"


def _inspect_get(response) -> dict:
    encoding = _content_encoding_class(response)
    brotli_present = _brotli_decoder_present()
    decodable = _body_decodable(response, encoding, brotli_present)
    info = {
        "get_content_encoding_class": encoding,
        "get_body_decodable": decodable,
        "brotli_decoder_present": brotli_present,
    }
    if not decodable:
        info.update({
            "get_form_action_class": "not-decoded",
            "get_password_control": "not-decoded",
            "get_username_control": "not-decoded",
            "get_hidden_count_class": "not-decoded",
            "get_challenge_class": "not-decoded",
        })
        return info
    text = response.text
    info.update({
        "get_form_action_class": _form_action_class(text),
        "get_password_control": _password_control(text),
        "get_username_control": _username_control(text),
        "get_hidden_count_class": _hidden_count_class(text),
        "get_challenge_class": _challenge_class(text),
    })
    return info


def _diagnostic_flags(text: str) -> dict[str, bool]:
    """Booleans only. The page text is not returned."""
    soup = BeautifulSoup(text or "", "html.parser")
    form = soup.find("form", action=lambda value: isinstance(value, str) and value.lower() == "/login/index/")
    password = soup.find("input", {"type": "password"})
    folded = re.sub(r"\s+", " ", text or "").casefold()
    return {
        "has_login_form": form is not None or password is not None,
        "has_account": "account settings" in folded,
        "has_logout": "log out" in folded or "logout" in folded,
    }


def _diagnostic_view(response, get_info: dict, observed_stage: str) -> dict:
    """Allowlisted fields only. No host, path, query, header, or body text."""
    parts = urlsplit(str(response.url))
    flags = _diagnostic_flags(response.text if get_info.get("get_body_decodable") or observed_stage == "post" else "")
    if observed_stage == "get" and not get_info.get("get_body_decodable"):
        flags = {
            "has_login_form": False,
            "has_account": False,
            "has_logout": False,
        }
    view = {
        "status_code": response.status_code,
        "host_class": _host_class(parts.hostname),
        "path_class": _path_class(parts.path),
        "content_type": _media_type(response.headers.get("content-type", "")),
        "has_login_form": flags["has_login_form"],
        "has_account": flags["has_account"],
        "has_logout": flags["has_logout"],
        "observed_stage": observed_stage,
        "final_content_encoding_class": _content_encoding_class(response),
    }
    view.update(get_info)
    return view


def _empty_diagnostic(error: str) -> dict:
    return {
        "error": error,
        "status_code": None,
        "host_class": "other",
        "path_class": "other",
        "content_type": "",
        "has_login_form": False,
        "has_account": False,
        "has_logout": False,
        "observed_stage": "not-reached",
        "get_form_action_class": "not-decoded",
        "get_password_control": "not-decoded",
        "get_username_control": "not-decoded",
        "get_hidden_count_class": "not-decoded",
        "get_challenge_class": "not-decoded",
        "get_content_encoding_class": "absent",
        "get_body_decodable": False,
        "final_content_encoding_class": "absent",
        "brotli_decoder_present": _brotli_decoder_present(),
    }


class _bounded_diagnostic_logs:
    """Drop all log records for one diagnostic call, then restore the manager."""

    def __enter__(self):
        self._previous = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        return self

    def __exit__(self, exc_type, exc, tb):
        logging.disable(self._previous)
        return False


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

    async def diagnose_login(self, target_url: str) -> dict:
        """Observe one ordinary login attempt and return only safe fields.

        For an authorized local run. This does not decide whether login
        succeeded, and it does not change ``login()``. The result uses
        host and path classifications, an allowlisted media type, and
        booleans for a login form, account settings, and log out.
        Credentials, request bodies, headers, cookies, tokens, raw pages,
        and URL components are not logged or returned.
        """
        if not self.username or not self.password:
            return _empty_diagnostic("credentials_not_configured")

        client = await self._get_client()
        try:
            with _bounded_diagnostic_logs():
                resp = await client.get(target_url)
                get_info = _inspect_get(resp)
                if resp.status_code != 200 or not get_info["get_body_decodable"]:
                    return _diagnostic_view(resp, get_info, "get")
                if get_info["get_challenge_class"] != "none":
                    return _diagnostic_view(resp, get_info, "get")
                if get_info["get_form_action_class"] != "exact-relative":
                    return _diagnostic_view(resp, get_info, "get")
                soup = BeautifulSoup(resp.text, "html.parser")
                form = soup.find("form", {"action": "/login/Index/"})
                if not form:
                    return _diagnostic_view(resp, get_info, "get")
                form_data = {}
                for inp in form.find_all("input", {"type": "hidden"}):
                    name = inp.get("name")
                    if name:
                        form_data[name] = inp.get("value", "")
                form_data["Username"] = self.username
                form_data["Password"] = self.password
                form_data["RememberMe"] = "false"
                result = await client.post(
                    "https://www.nccn.org/login/Index/",
                    data=form_data,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Referer": "https://www.nccn.org/",
                        "Origin": "https://www.nccn.org",
                    },
                )
                return _diagnostic_view(result, get_info, "post")
        except Exception:
            return _empty_diagnostic("request_failed")

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

    async def download_and_archive(
        self,
        pdf_url: str,
        slug: str,
        version: str,
        name: str = "",
        archive_dir: str | Path = "~/.nccn-monitor/archive",
        filename: str = "",
    ) -> Path | None:
        """Download a PDF and store it in the versioned archive.

        Archive structure:
            archive/{slug}/v{version}/NCCN_<CamelCase>_<Year>.V<Num>_EN.pdf
            archive/{slug}/v{version}/meta.json

        Args:
            pdf_url: URL to download.
            slug: Filesystem-safe guideline identifier.
            version: Version string like "2.2026".
            name: Full guideline name (for generating filename).
            archive_dir: Root archive directory.
            filename: Override filename. If empty, auto-generated from name+version.

        Returns the archived PDF path on success, None on failure.
        """
        from .scraper import format_pdf_filename

        archive_path = Path(archive_dir).expanduser() / slug / f"v{version}"

        # Determine filename
        if not filename and name:
            filename = format_pdf_filename(name, version)
        elif not filename:
            filename = "guideline.pdf"

        pdf_path = archive_path / filename
        existing = classify_current_archive(slug, version, name, archive_dir, filename)
        if existing == ARCHIVE_VALID:
            logger.info("Already archived: %s v%s", slug, version)
            return pdf_path
        if existing == ARCHIVE_BLOCKED_INVALID_EXISTING:
            logger.error("%s: %s v%s", BLOCKED_EXISTING_PDF_MESSAGE, slug, version)
            return None

        # Download to temp cache first, then move to archive
        temp_dir = Path(archive_dir).expanduser() / ".tmp"
        downloaded = await self.download_pdf(pdf_url, temp_dir, max_age_days=0)
        if not downloaded:
            return None

        if not professional_pdf_matches(downloaded, name, version):
            logger.error(
                "Rejected download for %s v%s: file is not the matching professional PDF",
                slug,
                version,
            )
            if downloaded.exists() and downloaded.resolve() != pdf_path.resolve():
                downloaded.unlink()
            return None

        # Only a non-PDF occupant of this exact path may be removed. An existing
        # %PDF is never deleted or overwritten, even if this download is valid.
        archive_path.mkdir(parents=True, exist_ok=True)
        if pdf_path.exists() and file_starts_with_pdf(pdf_path):
            if downloaded.exists() and downloaded.resolve() != pdf_path.resolve():
                downloaded.unlink()
            if professional_pdf_matches(pdf_path, name, version):
                return pdf_path
            logger.error("%s: %s v%s", BLOCKED_EXISTING_PDF_MESSAGE, slug, version)
            return None
        if pdf_path.exists():
            pdf_path.unlink()
        shutil.move(str(downloaded), str(pdf_path))

        # Write metadata
        meta = {
            "version": version,
            "slug": slug,
            "name": name,
            "filename": filename,
            "pdf_url": pdf_url,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "size_bytes": pdf_path.stat().st_size,
        }
        meta_path = archive_path / "meta.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        logger.info("Archived: %s → %s (%d bytes)", filename, archive_path, meta["size_bytes"])
        return pdf_path

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# ── Archive utilities ────────────────────────────────────────────


def get_archived_versions(
    slug: str, archive_dir: str | Path = "~/.nccn-monitor/archive"
) -> list[dict]:
    """List all archived versions for a guideline, newest first.

    Returns list of dicts with version, downloaded_at, size_bytes, path.
    """
    archive_path = Path(archive_dir).expanduser() / slug
    if not archive_path.exists():
        return []

    versions = []
    for version_dir in sorted(archive_path.iterdir(), reverse=True):
        if not version_dir.is_dir() or version_dir.name.startswith("."):
            continue
        meta_path = version_dir / "meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            # Find the actual PDF file (could be renamed)
            pdf_file = meta.get("filename", "guideline.pdf")
            actual_path = version_dir / pdf_file
            if not _listable_archive_file(actual_path):
                pdfs = [path for path in version_dir.glob("*.pdf") if _listable_archive_file(path)]
                if not pdfs:
                    continue
                actual_path = pdfs[0]
            meta_name = meta.get("name") or ""
            meta_version = meta.get("version") or ""
            if (
                file_starts_with_pdf(actual_path)
                and meta_name
                and meta_version
                and not professional_pdf_matches(actual_path, meta_name, meta_version)
            ):
                continue
            meta["pdf_path"] = str(actual_path)
            versions.append(meta)
        else:
            # No meta.json — find any non-HTML PDF-like file
            pdfs = [path for path in version_dir.glob("*.pdf") if _listable_archive_file(path)]
            if pdfs:
                versions.append({
                    "version": version_dir.name.lstrip("v"),
                    "pdf_path": str(pdfs[0]),
                    "filename": pdfs[0].name,
                    "size_bytes": pdfs[0].stat().st_size,
                })

    return versions
