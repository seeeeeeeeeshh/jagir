"""Drives a Playwright browser through the user's own already-logged-in
LinkedIn session to read job listings. This module never touches
credentials — it launches a *persistent* browser profile so a login the
user performs by hand survives across runs, and `ensure_logged_in` only
checks state, never submits one.

SELECTOR STRATEGY: LinkedIn's card wrapper and text elements use randomly-
hashed CSS module class names (e.g. "_4b4f6d9a") that change on every
deploy, so list scraping deliberately avoids matching on any class name.
Instead it walks every a[href*="/jobs/view/"] link on the page and keeps
only the ones that wrap at least two <p> elements (title, then
"Company · Location") — the other /jobs/view/ link on each card (the
"Apply" button) wraps an icon and a <span>, no <p> at all, so this filter
reliably picks out just the title link. Verified against real captured
markup — see tests/fixtures/html/saved_job_card.html and
tests/fixtures/html/applied_job_card.html plus
tests/test_linkedin_scraper_parsing.py. The list itself is numbered
pagination, not infinite scroll (also confirmed against a real account —
see _scrape_job_links). Further <p> lines after title/company-location
("Applied 1w ago", "(Posted 2w ago)"/"Reposted 1w ago") give an
approximate date_applied/posting_date — see _parse_relative_linkedin_date.
Job-detail-page selectors (_parse_detail_page) are still an unverified
best-effort guess, since capturing a real detail page's markup hasn't
happened yet — if scrape_job_detail comes back mostly empty, inspect a
real detail page and update _parse_detail_page the same way. Mirrors
app/sync/bookmarklet_js.py and extension/popup.js — keep all three in
sync if you adjust one.
"""

from __future__ import annotations

import random
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.sync_api import BrowserContext, Page, sync_playwright

from app.core.retry import network_retry
from app.sync.scraped_types import ScrapedJobDetail, ScrapedJobListRow

LINKEDIN_BASE = "https://www.linkedin.com"
# Confirmed directly against a real account: both lists live at the same
# path with a query param, not separate path segments as earlier assumed.
SAVED_JOBS_URL = f"{LINKEDIN_BASE}/jobs-tracker/?stage=saved"
APPLIED_JOBS_URL = f"{LINKEDIN_BASE}/jobs-tracker/?stage=applied"
FEED_URL = f"{LINKEDIN_BASE}/feed/"

# Tracking/session query params LinkedIn appends to job URLs — stripped so
# the same posting reached via search vs. a saved-jobs list resolves to the
# same canonical_linkedin_url.
_TRACKING_PARAM_PREFIXES = ("trk", "refid", "trackingid", "midtoken", "midsig", "lici")


def canonicalize_linkedin_url(url: str) -> str:
    """Strip query/tracking params from a LinkedIn job URL. Pure function,
    no browser dependency — fully unit-testable."""
    parts = urlsplit(url)
    kept = [
        (k, v)
        for k, v in [p.split("=", 1) if "=" in p else (p, "") for p in parts.query.split("&") if p]
        if k.lower() not in _TRACKING_PARAM_PREFIXES
    ]
    new_query = "&".join(f"{k}={v}" if v else k for k, v in kept)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), new_query, ""))


def extract_job_id_from_url(url: str) -> str | None:
    """LinkedIn job URLs commonly embed the numeric job id as
    /jobs/view/<id>/. Falls back to None if the pattern isn't found —
    canonical_linkedin_url remains the fallback identity in that case."""
    match = re.search(r"/jobs/view/(\d+)", url)
    return match.group(1) if match else None


def launch_browser(profile_dir: Path, headless: bool):
    """Returns (playwright_context_manager, browser_context). Caller is
    responsible for closing both. A persistent profile directory means the
    user's manual LinkedIn login (cookies/session) survives across runs —
    this function never submits or stores a password."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(str(profile_dir), headless=headless)
    return pw, context


def close_browser(pw, context: BrowserContext) -> None:
    context.close()
    pw.stop()


def _goto(page: Page, url: str, settle_ms: int = 2500) -> None:
    """Navigate and wait for content, without depending on the
    `domcontentloaded` lifecycle event — confirmed by direct testing that
    LinkedIn's pages never fire it in a way Playwright observes (the page
    renders and is fully usable well before that event would arrive; the
    event itself appears to be the thing that hangs, not the page load).
    `commit` fires as soon as the navigation response is committed, then we
    give the SPA a short settle window to render before reading content.
    """
    page.goto(url, wait_until="commit", timeout=15000)
    try:
        page.wait_for_load_state("load", timeout=settle_ms)
    except Exception:
        pass  # best-effort settle; proceed with whatever rendered


def ensure_logged_in(context: BrowserContext, page: Page) -> bool:
    """Checks whether the persistent session is authenticated, navigating
    the given page (left open either way — on False, the caller should
    leave it on-screen so the user can log in by hand in that same window;
    never attempts to log in itself).

    Uses the post-navigation URL rather than a CSS selector: LinkedIn
    redirects an unauthenticated request to /login server-side, and that
    redirect is already resolved by the time `wait_until="commit"` returns
    (confirmed directly: page.url was already the /uas/login URL right
    after commit, ~4.5s) — no need to wait for any element to render, and
    no selector to get wrong."""
    page.goto(FEED_URL, wait_until="commit", timeout=15000)
    return "login" not in page.url.lower()


@network_retry
def scrape_saved_jobs_list(page: Page, max_items: int) -> list[ScrapedJobListRow]:
    _goto(page, SAVED_JOBS_URL)
    return _scrape_job_links(page, max_items)


@network_retry
def scrape_applied_jobs_list(page: Page, max_items: int) -> list[ScrapedJobListRow]:
    _goto(page, APPLIED_JOBS_URL)
    rows = _scrape_job_links(page, max_items)
    for row in rows:
        row.date_applied = row.date_applied or "unknown"
        row.application_status_shown = row.application_status_shown or "Applied"
    return rows


_MAX_PAGES = 50
_NEXT_BUTTON_SELECTOR = '[data-testid="pagination-controls-next-button-visible"]'


def _scrape_job_links(page: Page, max_items: int) -> list[ScrapedJobListRow]:
    """LinkedIn's saved/applied list is numbered pagination (a "1 2 3 Next"
    control), not infinite scroll — confirmed directly: the real page's
    Next button carries data-testid="pagination-controls-next-button-visible",
    a deliberate test hook that should be far more stable across deploys
    than the surrounding hashed CSS classes. Clicks through every page,
    merging by URL, pausing with jitter — not machine-speed — between
    clicks, until the Next button is gone, `max_items` is reached, or a
    safety cap is hit. Mirrors the identical loop in extension/popup.js and
    app/sync/bookmarklet_js.py."""
    rows_by_url: dict[str, ScrapedJobListRow] = {}
    for _ in range(_MAX_PAGES):
        links = page.locator("a[href*='/jobs/view/']")
        for i in range(links.count()):
            outer_html = links.nth(i).evaluate("el => el.outerHTML")
            row = _parse_job_link(outer_html)
            if row is not None and row.linkedin_url:
                rows_by_url[row.linkedin_url] = row
        if len(rows_by_url) >= max_items:
            break
        next_button = page.locator(_NEXT_BUTTON_SELECTOR)
        if next_button.count() == 0:
            break
        next_button.first.click()
        page.wait_for_timeout(1200 + random.random() * 800)
    return list(rows_by_url.values())[:max_items]


@network_retry
def scrape_job_detail(page: Page, job_url: str) -> ScrapedJobDetail:
    _goto(page, job_url)
    return _parse_detail_page(page.content())


_RELATIVE_DATE_RE = re.compile(
    r"(\d+)\s*(min|mins|minute|minutes|hr|hrs|hour|hours|h|d|day|days|"
    r"w|wk|wks|week|weeks|mo|mos|month|months|y|yr|yrs|year|years)\b",
    re.IGNORECASE,
)


def _parse_relative_linkedin_date(text: str, today: date | None = None) -> str | None:
    """"Applied 1w ago" / "(Posted 2w ago)" / "Reposted 1w ago" -> an
    approximate ISO date. LinkedIn only ever gives a relative time, never
    an exact date, so this is inherently approximate — still far more
    useful than no date at all for sorting/urgency purposes. Mirrors the JS
    version in extension/popup.js and app/sync/bookmarklet_js.py exactly —
    keep all three in sync if you adjust one."""
    match = _RELATIVE_DATE_RE.search(text)
    if not match:
        return None
    n = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("min"):
        days = 0
    elif unit.startswith("mo"):
        days = n * 30
    elif unit.startswith("h"):
        days = 0
    elif unit.startswith("d"):
        days = n
    elif unit.startswith("w"):
        days = n * 7
    elif unit.startswith("y"):
        days = n * 365
    else:
        return None
    return ((today or date.today()) - timedelta(days=days)).isoformat()


def _parse_job_link(html: str) -> ScrapedJobListRow | None:
    """Parses one a[href*='/jobs/view/'] link's outer HTML via BeautifulSoup.
    Kept as a pure string->dataclass function (not inline Playwright locator
    calls) so it can be exercised offline against saved fixture HTML — see
    tests/test_linkedin_scraper_parsing.py. Returns None for a link that
    isn't a title card (e.g. the "Apply" button, which points at the same
    job but wraps no <p> elements — see this module's docstring)."""
    soup = BeautifulSoup(html, "lxml")
    link = soup.find("a")
    if link is None:
        return None

    paragraphs = link.find_all("p")
    if len(paragraphs) < 2:
        return None

    href = link.get("href")
    linkedin_url = f"{LINKEDIN_BASE}{href}" if href and href.startswith("/") else href
    linkedin_job_id = extract_job_id_from_url(linkedin_url) if linkedin_url else None

    title = _text(paragraphs[0]) or "Unknown title"
    company_location = _text(paragraphs[1]) or ""
    if "·" in company_location:
        company, _, location = company_location.partition("·")
        company, location = company.strip(), location.strip() or None
    else:
        company, location = company_location, None

    # Any further <p> lines are matched by text prefix, not position — the
    # Saved list only ever has one extra line (posting recency, no applied-
    # date concept at all), the Applied list has two.
    date_applied = None
    posting_date = None
    for extra_p in paragraphs[2:]:
        extra = _text(extra_p) or ""
        stripped = extra.lstrip("(").strip()
        if stripped.lower().startswith("applied"):
            date_applied = _parse_relative_linkedin_date(extra)
        elif stripped.lower().startswith(("posted", "reposted")):
            posting_date = _parse_relative_linkedin_date(extra)

    return ScrapedJobListRow(
        linkedin_job_id=linkedin_job_id,
        linkedin_url=linkedin_url,
        title=title,
        company_name=company or "Unknown company",
        location=location,
        date_applied=date_applied,
        posting_date=posting_date,
    )


def _parse_detail_page(html: str) -> ScrapedJobDetail:
    soup = BeautifulSoup(html, "lxml")

    description_el = soup.select_one(".jobs-description__content, .description__text")
    salary_el = soup.select_one(".jobs-unified-top-card__salary, .salary")
    criteria_els = soup.select(".jobs-unified-top-card__job-insight, .job-criteria__text")

    criteria_text = " ".join(_text(el) or "" for el in criteria_els)
    workplace_type = next((w for w in ("Remote", "Hybrid", "On-site") if w.lower() in criteria_text.lower()), None)
    employment_type = next(
        (w for w in ("Full-time", "Part-time", "Internship", "Contract") if w.lower() in criteria_text.lower()), None
    )

    return ScrapedJobDetail(
        workplace_type=workplace_type,
        employment_type=employment_type,
        salary_text=_text(salary_el),
        job_description=_text(description_el),
        easy_apply=1 if "easy apply" in html.lower() else None,
        raw_metadata={},
    )


def _text(el) -> str | None:
    if el is None:
        return None
    t = el.get_text(strip=True)
    return t or None


def to_scraped_job(
    list_row: ScrapedJobListRow,
    detail: ScrapedJobDetail | None,
):
    """Pure merge of a list row + optional detail-page data into the
    matcher's ScrapedJob shape. No browser dependency."""
    from app.sync.scraped_types import ScrapedJob  # local import avoids a cycle at module load time

    canonical_url = canonicalize_linkedin_url(list_row.linkedin_url) if list_row.linkedin_url else None

    return ScrapedJob(
        linkedin_job_id=list_row.linkedin_job_id,
        linkedin_url=list_row.linkedin_url,
        canonical_linkedin_url=canonical_url,
        title=list_row.title,
        company_name=list_row.company_name,
        location=list_row.location,
        workplace_type=detail.workplace_type if detail else None,
        employment_type=detail.employment_type if detail else None,
        salary_text=detail.salary_text if detail else None,
        job_description=detail.job_description if detail else None,
        date_applied=list_row.date_applied,
        date_saved=list_row.date_saved,
        # The detail page's own posting_date (when a detail fetch happened
        # to run for this row) wins as the more authoritative source; the
        # list row's own relative-time-derived estimate is the fallback.
        posting_date=(detail.posting_date if detail else None) or list_row.posting_date,
        easy_apply=detail.easy_apply if detail else None,
        external_apply_url=detail.external_apply_url if detail else None,
        application_status_shown=list_row.application_status_shown,
        recruiter_name=detail.recruiter_name if detail else None,
        raw_metadata=detail.raw_metadata if detail else {},
    )
