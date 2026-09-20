"""Validates that the scraper's parsing logic extracts the fields it is
told to look for from HTML fixtures. saved_job_card.html is a trimmed-down
copy of real markup captured from a live LinkedIn account (see
linkedin_scraper.py's module docstring for the selector strategy this
verifies); job_detail_page.html is still hand-authored/unverified. These
tests exist to catch parsing regressions, not to re-certify the scraper
against the live site on every run.
"""

from pathlib import Path

from bs4 import BeautifulSoup

from datetime import date, timedelta

from app.sync.linkedin_scraper import (
    _NEXT_BUTTON_SELECTOR,
    _parse_detail_page,
    _parse_job_link,
    _parse_relative_linkedin_date,
    _scrape_job_links,
    canonicalize_linkedin_url,
    extract_job_id_from_url,
)

FIXTURES = Path(__file__).parent / "fixtures" / "html"


def test_parse_job_link_extracts_expected_fields():
    html = (FIXTURES / "saved_job_card.html").read_text(encoding="utf-8")
    soup_links = BeautifulSoup(html, "lxml").select("a[href*='/jobs/view/']")
    # the fixture includes both the title link and the decoy "Apply" link,
    # exactly like a real card — parse only the title one here (integration
    # coverage of picking the right one lives in test_scrape_job_links_*)
    title_link_html = str(soup_links[0])
    row = _parse_job_link(title_link_html)

    assert row is not None
    assert row.title == "AI Automation & Operations Intelligence Intern - Regional SPX Express (Spring 2026)"
    assert row.company_name == "SPX Express"
    assert row.location == "Singapore (On-site)"
    assert row.linkedin_job_id == "4432228284"
    assert row.linkedin_url == "https://www.linkedin.com/jobs/view/4432228284/"


def test_parse_job_link_rejects_link_without_two_paragraphs():
    html = (FIXTURES / "saved_job_card.html").read_text(encoding="utf-8")
    soup_links = BeautifulSoup(html, "lxml").select("a[href*='/jobs/view/']")
    apply_link_html = str(soup_links[1])  # the "Apply" button — no <p> at all

    assert _parse_job_link(apply_link_html) is None


def test_parse_job_link_saved_card_has_no_date_applied():
    """The Saved list's third line ("Reposted 1w ago") is about the
    posting's own age, not when the user saved it — real markup, no
    "date saved" signal exists on this card at all."""
    html = (FIXTURES / "saved_job_card.html").read_text(encoding="utf-8")
    row = _parse_job_link(html)

    assert row.date_applied is None
    assert row.posting_date is not None  # "Reposted 1w ago" still routes here


def test_parse_job_link_applied_card_extracts_both_dates():
    """Regression test: real markup from an Applied Jobs list card shows
    "Applied 1w ago" and "(Posted 2w ago)" as two further <p> lines inside
    the same title link — this was previously never read at all, so
    date_applied stayed permanently empty for every LinkedIn-imported
    record regardless of which list it came from."""
    html = (FIXTURES / "applied_job_card.html").read_text(encoding="utf-8")
    row = _parse_job_link(html)

    assert row is not None
    assert row.title == "Business Data Analyst (Automation & Business Insights) - Trust and Safety"
    assert row.company_name == "TikTok"
    assert row.date_applied == (date.today() - timedelta(days=7)).isoformat()
    assert row.posting_date == (date.today() - timedelta(days=14)).isoformat()


def test_parse_relative_linkedin_date_units():
    today = date(2026, 9, 15)

    assert _parse_relative_linkedin_date("Applied 1w ago", today) == "2026-09-08"
    assert _parse_relative_linkedin_date("(Posted 2w ago)", today) == "2026-09-01"
    assert _parse_relative_linkedin_date("Applied 3d ago", today) == "2026-09-12"
    assert _parse_relative_linkedin_date("Applied 2mo ago", today) == "2026-07-17"
    assert _parse_relative_linkedin_date("Applied 1y ago", today) == "2025-09-15"
    assert _parse_relative_linkedin_date("(Reposted 21h ago)", today) == "2026-09-15"  # same day
    assert _parse_relative_linkedin_date("gibberish", today) is None


class _FakeNth:
    def __init__(self, html):
        self._html = html

    def evaluate(self, _js):
        return self._html


class _FakeLinksLocator:
    def __init__(self, get_htmls):
        self._get_htmls = get_htmls

    def count(self):
        return len(self._get_htmls())

    def nth(self, i):
        return _FakeNth(self._get_htmls()[i])


class _FakeNextButton:
    def __init__(self, state):
        self._state = state

    def click(self):
        self._state["current"] += 1
        self._state["click_count"] += 1


class _FakeNextLocator:
    def __init__(self, state, num_pages):
        self._state = state
        self._num_pages = num_pages

    def count(self):
        return 1 if self._state["current"] < self._num_pages - 1 else 0

    @property
    def first(self):
        return _FakeNextButton(self._state)


class _FakePaginatedPage:
    """Fake Playwright Page over a list of per-page link-HTML lists,
    exposing a Next button (via data-testid, like the real page) that
    disappears once the last page is reached — same shape
    _scrape_job_links's pagination-click loop expects."""

    def __init__(self, pages: list[list[str]]):
        self._pages = pages
        self.state = {"current": 0, "click_count": 0}

    def locator(self, selector):
        if selector == _NEXT_BUTTON_SELECTOR:
            return _FakeNextLocator(self.state, len(self._pages))
        return _FakeLinksLocator(lambda: self._pages[self.state["current"]])

    def wait_for_timeout(self, _ms):
        pass  # skip the real pacing delay in tests


def _title_link_html(job_id: str) -> str:
    html = (FIXTURES / "saved_job_card.html").read_text(encoding="utf-8")
    link = str(BeautifulSoup(html, "lxml").select("a[href*='/jobs/view/']")[0])
    return link.replace("4432228284", job_id)


def test_scrape_job_links_picks_title_link_and_skips_apply_link():
    """Single page (no Next button) — the fixture's Apply-link decoy must
    be filtered out, exercising the same dedup/filter path
    _scrape_job_links uses."""
    html = (FIXTURES / "saved_job_card.html").read_text(encoding="utf-8")
    link_htmls = [str(link) for link in BeautifulSoup(html, "lxml").select("a[href*='/jobs/view/']")]
    page = _FakePaginatedPage([link_htmls])

    rows = _scrape_job_links(page, max_items=10)

    assert len(rows) == 1
    assert rows[0].title.startswith("AI Automation")


def test_scrape_job_links_clicks_through_multiple_pages_and_merges():
    """Simulates LinkedIn's numbered pagination: 3 pages of results behind
    a Next button that disappears on the last page."""
    pages = [[_title_link_html("1001")], [_title_link_html("1002")], [_title_link_html("1003")]]
    page = _FakePaginatedPage(pages)

    rows = _scrape_job_links(page, max_items=100)

    assert {r.linkedin_job_id for r in rows} == {"1001", "1002", "1003"}
    assert page.state["current"] == 2  # walked all the way to the last page
    assert page.state["click_count"] == 2  # clicked Next exactly twice for 3 pages


def test_scrape_job_links_stops_early_once_max_items_reached():
    pages = [[_title_link_html("2001")], [_title_link_html("2002")], [_title_link_html("2003")]]
    page = _FakePaginatedPage(pages)

    rows = _scrape_job_links(page, max_items=1)

    assert len(rows) == 1
    assert page.state["click_count"] == 0  # stopped before ever clicking Next


def test_parse_detail_page_extracts_expected_fields():
    html = (FIXTURES / "job_detail_page.html").read_text(encoding="utf-8")
    detail = _parse_detail_page(html)

    assert detail.workplace_type == "Remote"
    assert detail.employment_type == "Internship"
    assert detail.salary_text == "$40/hr - $55/hr"
    assert "distributed systems" in detail.job_description
    assert detail.easy_apply == 1


def test_canonicalize_linkedin_url_strips_tracking_params():
    dirty = "https://www.linkedin.com/jobs/view/4123456789/?trk=flagship3&refId=abc123&geoId=103644278"
    clean = canonicalize_linkedin_url(dirty)

    assert "trk=" not in clean
    assert "refId=" not in clean
    assert clean.startswith("https://www.linkedin.com/jobs/view/4123456789")


def test_canonicalize_linkedin_url_same_job_different_tracking_matches():
    a = canonicalize_linkedin_url("https://www.linkedin.com/jobs/view/4123456789/?trk=srp_a")
    b = canonicalize_linkedin_url("https://www.linkedin.com/jobs/view/4123456789/?trk=saved_jobs_b&refId=xyz")

    assert a == b


def test_extract_job_id_from_url():
    assert extract_job_id_from_url("https://www.linkedin.com/jobs/view/4123456789/") == "4123456789"
    assert extract_job_id_from_url("https://www.linkedin.com/jobs/search/?keywords=intern") is None
