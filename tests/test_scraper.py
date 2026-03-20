"""Tests for the NCCN scraper module."""

from pathlib import Path

from nccn_monitor.scraper import (
    parse_category_page,
    parse_recently_published,
    ScrapeError,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── Category page tests (primary data source) ───────────────────────


def test_parse_category_page_extracts_all_items():
    html = (FIXTURES / "category_page.html").read_text()
    results = parse_category_page(html, "Cancer by Type")

    assert len(results) == 5
    names = [g.name for g in results]
    assert "Non-Small Cell Lung Cancer" in names
    assert "Breast Cancer" in names
    assert "Prostate Cancer" in names


def test_parse_category_page_extracts_versions():
    html = (FIXTURES / "category_page.html").read_text()
    results = parse_category_page(html, "Cancer by Type")

    by_name = {g.name: g for g in results}
    assert by_name["Non-Small Cell Lung Cancer"].version == "5.2026"
    assert by_name["Colon Cancer"].version == "1.2026"


def test_parse_category_page_builds_detail_urls():
    html = (FIXTURES / "category_page.html").read_text()
    results = parse_category_page(html, "Cancer by Type")

    by_name = {g.name: g for g in results}
    assert by_name["Gastric Cancer"].detail_url == (
        "https://www.nccn.org/guidelines/guidelines-detail?category=1&id=1003"
    )


def test_parse_category_page_sets_category():
    html = (FIXTURES / "category_page.html").read_text()
    results = parse_category_page(html, "Supportive Care")

    assert all(g.category == "Supportive Care" for g in results)


def test_parse_category_page_both_columns():
    """Ensure items from both col-md-6 columns are extracted."""
    html = (FIXTURES / "category_page.html").read_text()
    results = parse_category_page(html, "Cancer by Type")

    # Items from left column (3) and right column (2)
    assert len(results) == 5


def test_parse_category_page_empty_raises():
    try:
        parse_category_page("<html><body></body></html>", "Test")
        assert False, "Should have raised ScrapeError"
    except ScrapeError:
        pass


# ── Recently Published page tests (secondary data source) ───────────


def test_parse_recently_published_extracts_all_guidelines():
    html = (FIXTURES / "recently_published.html").read_text()
    results = parse_recently_published(html)

    assert len(results) == 5
    names = [g.name for g in results]
    assert "Non-Small Cell Lung Cancer" in names
    assert "Breast Cancer" in names
    assert "Antiemesis" in names


def test_parse_recently_published_extracts_versions():
    html = (FIXTURES / "recently_published.html").read_text()
    results = parse_recently_published(html)

    by_name = {g.name: g for g in results}
    assert by_name["Non-Small Cell Lung Cancer"].version == "5.2026"
    assert by_name["Lung Cancer Screening"].version == "1.2026"


def test_parse_recently_published_tracks_categories():
    html = (FIXTURES / "recently_published.html").read_text()
    results = parse_recently_published(html)

    by_name = {g.name: g for g in results}
    assert by_name["Non-Small Cell Lung Cancer"].category == "Guidelines for Treatment of Cancer by Type"
    assert by_name["Antiemesis"].category == "Guidelines for Supportive Care"


def test_parse_empty_html_raises_scrape_error():
    try:
        parse_recently_published("<html><body><div class='content'></div></body></html>")
        assert False, "Should have raised ScrapeError"
    except ScrapeError:
        pass
