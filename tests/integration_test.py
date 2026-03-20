#!/usr/bin/env python3
"""Integration test — run against live NCCN website.

Usage:
    export NCCN_USERNAME="your_email"
    export NCCN_PASSWORD="your_password"
    python tests/integration_test.py

Tests run sequentially:
  1. Scrape Recently Published page (no login needed)
  2. State change detection (local only)
  3. NCCN login + PDF download (needs credentials)
  4. PDF update notes extraction
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nccn_monitor.scraper import fetch_all_guidelines, fetch_recently_published, ScrapeError
from nccn_monitor.state import StateManager
from nccn_monitor.downloader import NCCNDownloader
from nccn_monitor.analyzer import extract_update_notes


def header(msg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def fail(msg: str) -> None:
    print(f"  ❌ {msg}")


def info(msg: str) -> None:
    print(f"  ℹ️  {msg}")


async def test_scraper():
    """Test 1: Scrape ALL NCCN category pages."""
    header("Test 1: Scrape all 4 NCCN category pages")

    try:
        guidelines = await fetch_all_guidelines()
        ok(f"Found {len(guidelines)} guidelines across 4 categories")

        # Show count per category
        from collections import Counter
        cats = Counter(g.category for g in guidelines)
        for cat, count in cats.items():
            info(f"{cat}: {count} guidelines")

        # Show first 5
        for g in guidelines[:5]:
            info(f"{g.name} — Version {g.version}")
        if len(guidelines) > 5:
            info(f"... and {len(guidelines) - 5} more")

        # Validate structure
        assert len(guidelines) >= 80, f"Expected 80+ guidelines, got {len(guidelines)}"
        assert all(g.version for g in guidelines), "Some guidelines missing version"
        assert all(g.detail_url for g in guidelines), "Some guidelines missing detail URL"
        ok("All guidelines have name, version, and detail URL")

        return guidelines

    except ScrapeError as e:
        fail(f"Scrape failed: {e}")
        fail("The NCCN page structure may have changed!")
        return None
    except Exception as e:
        fail(f"Unexpected error: {e}")
        return None


async def test_state(guidelines):
    """Test 2: State change detection."""
    header("Test 2: State change detection")

    if not guidelines:
        fail("Skipped — no guidelines from Test 1")
        return

    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        mgr = StateManager(state_file)

        # First run — baseline
        changes = mgr.detect_changes(guidelines)
        assert changes == [], f"First run should return no changes, got {len(changes)}"
        ok(f"First run: baseline established with {len(mgr.known_guidelines)} guidelines")

        # Second run — same data, no changes
        changes = mgr.detect_changes(guidelines)
        assert changes == [], f"Same data should return no changes, got {len(changes)}"
        ok("Second run: no changes detected (correct)")

        # Simulate a version change
        fake = list(guidelines)
        if fake:
            from nccn_monitor.scraper import GuidelineInfo
            original = fake[0]
            fake[0] = GuidelineInfo(
                name=original.name,
                version="99.9999",  # fake version
                detail_url=original.detail_url,
                category=original.category,
            )
            changes = mgr.detect_changes(fake)
            assert len(changes) == 1, f"Expected 1 change, got {len(changes)}"
            ok(f"Simulated change detected: {changes[0].name} {changes[0].old_version} → {changes[0].new_version}")


async def test_login_and_download(guidelines, cache_dir: str):
    """Test 3: NCCN login + PDF download."""
    header("Test 3: NCCN login + PDF download")

    username = os.getenv("NCCN_USERNAME")
    password = os.getenv("NCCN_PASSWORD")

    if not username or not password:
        fail("NCCN_USERNAME or NCCN_PASSWORD not set — skipping login test")
        info("Run: export NCCN_USERNAME=xxx NCCN_PASSWORD=xxx")
        return None

    if not guidelines:
        fail("Skipped — no guidelines from Test 1")
        return None

    # Use a known small PDF URL for testing
    test_pdf_url = "https://www.nccn.org/professionals/physician_gls/pdf/nmsc.pdf"
    info(f"Testing with: Basal Cell Skin Cancer ({test_pdf_url})")

    async with NCCNDownloader(username, password) as dl:
        pdf_path = await dl.download_pdf(test_pdf_url, cache_dir)

        if pdf_path:
            size_mb = pdf_path.stat().st_size / (1024 * 1024)
            ok(f"PDF downloaded: {pdf_path.name} ({size_mb:.1f} MB)")
            return pdf_path
        else:
            fail("PDF download failed")
            info("Check credentials and network connection")
            return None


async def test_analyzer(pdf_path):
    """Test 4: Extract update notes from PDF."""
    header("Test 4: PDF update notes extraction")

    if not pdf_path:
        fail("Skipped — no PDF from Test 3")
        return

    text = extract_update_notes(pdf_path, max_pages=3)

    if text:
        ok(f"Extracted {len(text)} chars from first 3 pages")
        # Show first 500 chars as preview
        preview = text[:500].replace("\n", "\n    ")
        info("Preview of extracted text:")
        print(f"    {preview}")
        if len(text) > 500:
            info(f"... ({len(text) - 500} more chars)")
    else:
        fail("No text extracted from PDF")
        info("The PDF might have a different structure than expected")


async def main():
    print("\n🔬 NCCN Monitor Integration Test")
    print("Testing against live NCCN website...\n")

    # Use a shared temp dir so PDF persists across tests
    with tempfile.TemporaryDirectory() as shared_tmp:
        # Test 1: Scraper
        guidelines = await test_scraper()

        # Test 2: State
        await test_state(guidelines)

        # Test 3: Login + Download
        pdf_path = await test_login_and_download(guidelines, shared_tmp)

        # Test 4: Analyzer
        await test_analyzer(pdf_path)

    header("Summary")
    print("  Integration test complete.")
    print("  Review the results above for any ❌ failures.\n")


if __name__ == "__main__":
    asyncio.run(main())
