"""Source for the LinkedIn capture bookmarklet (see app/ui/pages/sync_page.py
for where it's rendered as a draggable link). Kept as a single readable JS
string, not minified — the whole point of the bookmarklet approach is that
the user can edit this directly (via the browser's bookmark editor) if
LinkedIn's markup changes, without touching Python or Playwright.

Selectors mirror extension/popup.js's — keep them in sync if you adjust
one. LinkedIn's card wrapper and text elements use randomly-hashed CSS
module class names (e.g. "_4b4f6d9a") that change on every deploy, so this
deliberately avoids matching on any class name. Instead it walks every
a[href*="/jobs/view/"] link and keeps only the ones that wrap at least two
<p> elements (title, then "Company · Location") — the other /jobs/view/
link on each card (the "Apply" button) wraps an icon and a <span>, no <p>
at all, so this filter reliably picks out just the title link. Verified
against real captured markup — see tests/fixtures/html/saved_job_card.html,
tests/fixtures/html/applied_job_card.html, and
tests/test_linkedin_scraper_parsing.py. Further <p> lines after
title/company-location ("Applied 1w ago", "(Posted 2w ago)"/"Reposted 1w
ago") give an approximate date_applied/posting_date, parsed client-side
by parseRelativeLinkedInDate — LinkedIn only ever gives relative time, so
this is inherently approximate, but far better than no date at all.

LinkedIn's saved/applied list is numbered pagination (a "1 2 3 Next"
control), not infinite scroll — confirmed directly: the real page's Next
button carries data-testid="pagination-controls-next-button-visible", a
deliberate test hook that should be far more stable across deploys than
the surrounding hashed CSS classes. Clicks through every page, merging by
URL, pausing with jitter — not machine-speed — between clicks, until the
Next button is gone or a 50-page safety cap is hit, so a long list is
fully captured rather than just the first page's ~10 cards.
"""

CAPTURE_ENDPOINT = "http://localhost:8080/sync/capture"

_BOOKMARKLET_SOURCE = """
(async function() {
  var listType = location.href.indexOf('stage=applied') !== -1 ? 'applied' : 'saved';

  function parseRelativeLinkedInDate(text) {
    var match = text.match(/(\\d+)\\s*(min|mins|minute|minutes|hr|hrs|hour|hours|h|d|day|days|w|wk|wks|week|weeks|mo|mos|month|months|y|yr|yrs|year|years)\\b/i);
    if (!match) { return null; }
    var n = parseInt(match[1], 10);
    var unit = match[2].toLowerCase();
    var days;
    if (unit.indexOf('min') === 0) days = 0;
    else if (unit.indexOf('mo') === 0) days = n * 30;
    else if (unit[0] === 'h') days = 0;
    else if (unit[0] === 'd') days = n;
    else if (unit[0] === 'w') days = n * 7;
    else if (unit[0] === 'y') days = n * 365;
    else return null;
    var d = new Date();
    d.setDate(d.getDate() - days);
    return d.toISOString().slice(0, 10);
  }

  function collectFromCurrentPage() {
    var links = document.querySelectorAll("a[href*='/jobs/view/']");
    var items = [];
    links.forEach(function(link) {
      var paragraphs = link.querySelectorAll('p');
      if (paragraphs.length < 2) { return; }
      var href = link.getAttribute('href');
      if (!href) { return; }
      var url = href.indexOf('/') === 0 ? 'https://www.linkedin.com' + href : href;
      var title = paragraphs[0].textContent.trim();
      var companyLocation = paragraphs[1].textContent.trim();
      var dotIndex = companyLocation.indexOf('\\u00b7');
      var company = dotIndex === -1 ? companyLocation : companyLocation.slice(0, dotIndex).trim();
      var locationText = dotIndex === -1 ? null : companyLocation.slice(dotIndex + 1).trim();
      if (!title || !company) { return; }
      var dateApplied = null;
      var postingDate = null;
      for (var i = 2; i < paragraphs.length; i++) {
        var extra = paragraphs[i].textContent.trim();
        if (/^applied/i.test(extra)) { dateApplied = parseRelativeLinkedInDate(extra); }
        else if (/^\\(?\\s*(posted|reposted)/i.test(extra)) { postingDate = parseRelativeLinkedInDate(extra); }
      }
      items.push({
        title: title,
        company_name: company,
        location: locationText,
        linkedin_url: url,
        list_type: listType,
        date_applied: dateApplied,
        posting_date: postingDate
      });
    });
    return items;
  }

  function sleep(ms) { return new Promise(function(resolve) { setTimeout(resolve, ms); }); }

  var MAX_PAGES = 50;
  var allItemsByUrl = {};
  for (var page = 0; page < MAX_PAGES; page++) {
    collectFromCurrentPage().forEach(function(item) { allItemsByUrl[item.linkedin_url] = item; });
    var nextButton = document.querySelector('[data-testid="pagination-controls-next-button-visible"]');
    if (!nextButton) { break; }
    nextButton.click();
    await sleep(1200 + Math.random() * 800);
  }

  var items = Object.values(allItemsByUrl);
  if (items.length === 0) {
    alert('Jagir: found 0 job cards on this page. Make sure you are on your LinkedIn Saved Jobs or Applied Jobs list, then try again.');
    return;
  }
  var form = document.createElement('form');
  form.method = 'POST';
  form.action = '%(endpoint)s';
  form.target = '_blank';
  var input = document.createElement('input');
  input.type = 'hidden';
  input.name = 'payload';
  input.value = JSON.stringify(items);
  form.appendChild(input);
  document.body.appendChild(form);
  form.submit();
  document.body.removeChild(form);
})();
""" % {"endpoint": CAPTURE_ENDPOINT}


def bookmarklet_href() -> str:
    """A `javascript:` URI suitable for an <a href> — drag it to a bookmarks
    bar, or click it if you're already navigated to a LinkedIn jobs list."""
    # Collapse to one line and strip comments' surrounding whitespace; no
    # percent-encoding needed inside an HTML attribute value.
    minified = " ".join(line.strip() for line in _BOOKMARKLET_SOURCE.strip().splitlines())
    return "javascript:" + minified
