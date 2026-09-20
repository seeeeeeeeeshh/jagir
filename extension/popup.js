// Jagir — LinkedIn Capture popup.
//
// Click "Capture from this page" while viewing your LinkedIn Saved Jobs or
// Applied Jobs list: this injects captureLinkedInJobs() into that tab (the
// page you're already looking at — no separate browser, no stored cookies),
// POSTs the result to Jagir's local capture endpoint, and shows exactly
// what it found right here. Nothing happens until you click the button.
//
// Selectors mirror app/sync/bookmarklet_js.py and
// app/sync/linkedin_scraper.py — keep all three in sync if you adjust one.
// LinkedIn's card wrapper and text elements use randomly-hashed CSS module
// class names (e.g. "_4b4f6d9a") that change on every deploy, so this
// deliberately avoids matching on any class name. Instead it walks every
// a[href*="/jobs/view/"] link and keeps only the ones that wrap at least
// two <p> elements (title, then "Company · Location") — the other
// /jobs/view/ link on each card (the "Apply" button) wraps an icon and a
// <span>, no <p> at all, so this filter reliably picks out just the title
// link. If this shows 0 again, LinkedIn changed this structure too;
// inspect a real card (right-click -> Inspect) and adjust.
//
// Further <p> lines after title/company-location ("Applied 1w ago",
// "(Posted 2w ago)"/"Reposted 1w ago") give an approximate date_applied/
// posting_date — LinkedIn only ever shows relative time, never an exact
// date, so this is inherently approximate, but far better than no date at
// all (see parseRelativeLinkedInDate below).

const CAPTURE_ENDPOINT = "http://localhost:8080/sync/capture";

// Self-contained: chrome.scripting.executeScript's `func` runs in the page
// context with no access to anything outside this function body. Async so
// it can click through pagination and wait for each page to render.
async function captureLinkedInJobs() {
  // LinkedIn's saved/applied lists live at the same path with a query
  // param (/jobs-tracker/?stage=saved | ?stage=applied) — confirmed
  // directly against a real account, not a path segment as earlier
  // assumed. Defaults to "saved" for any other page.
  var listType = location.href.indexOf("stage=applied") !== -1 ? "applied" : "saved";

  // "Applied 1w ago" / "(Posted 2w ago)" / "Reposted 1w ago" — confirmed
  // directly against a real Applied Jobs list: these sit as extra <p> tags
  // inside the same title link, after title/company-location. Approximate
  // (LinkedIn only gives relative time, never an exact date), but a real
  // date beats no date at all — everything downstream that uses
  // date_applied was silently empty before this.
  function parseRelativeLinkedInDate(text) {
    var match = text.match(
      /(\d+)\s*(min|mins|minute|minutes|hr|hrs|hour|hours|h|d|day|days|w|wk|wks|week|weeks|mo|mos|month|months|y|yr|yrs|year|years)\b/i
    );
    if (!match) {
      return null;
    }
    var n = parseInt(match[1], 10);
    var unit = match[2].toLowerCase();
    var days;
    if (unit.indexOf("min") === 0) days = 0;
    else if (unit.indexOf("mo") === 0) days = n * 30;
    else if (unit[0] === "h") days = 0;
    else if (unit[0] === "d") days = n;
    else if (unit[0] === "w") days = n * 7;
    else if (unit[0] === "y") days = n * 365;
    else return null;
    var d = new Date();
    d.setDate(d.getDate() - days);
    return d.toISOString().slice(0, 10);
  }

  function collectFromCurrentPage() {
    var links = document.querySelectorAll("a[href*='/jobs/view/']");
    var items = [];
    links.forEach(function (link) {
      var paragraphs = link.querySelectorAll("p");
      if (paragraphs.length < 2) {
        return; // icon-only links (Apply, etc.) wrap no <p> at all
      }
      var href = link.getAttribute("href");
      if (!href) {
        return;
      }
      var url = href.indexOf("/") === 0 ? "https://www.linkedin.com" + href : href;
      var title = paragraphs[0].textContent.trim();
      var companyLocation = paragraphs[1].textContent.trim();
      var dotIndex = companyLocation.indexOf("·"); // "·" separates company from location
      var company = dotIndex === -1 ? companyLocation : companyLocation.slice(0, dotIndex).trim();
      var location_ = dotIndex === -1 ? null : companyLocation.slice(dotIndex + 1).trim();
      if (!title || !company) {
        return;
      }
      // Any further <p> lines are matched by text prefix, not position —
      // the Saved list only ever has one extra line (posting recency,
      // no applied-date concept at all), the Applied list has two.
      var dateApplied = null;
      var postingDate = null;
      for (var i = 2; i < paragraphs.length; i++) {
        var extra = paragraphs[i].textContent.trim();
        if (/^applied/i.test(extra)) {
          dateApplied = parseRelativeLinkedInDate(extra);
        } else if (/^\(?\s*(posted|reposted)/i.test(extra)) {
          postingDate = parseRelativeLinkedInDate(extra);
        }
      }
      items.push({
        title: title,
        company_name: company,
        location: location_,
        linkedin_url: url,
        list_type: listType,
        date_applied: dateApplied,
        posting_date: postingDate,
      });
    });
    return items;
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  // LinkedIn's saved/applied list is numbered pagination (a "1 2 3 Next"
  // control), not infinite scroll — confirmed directly: the real page's
  // Next button carries data-testid="pagination-controls-next-button-visible",
  // a deliberate test hook that should be far more stable across deploys
  // than the surrounding hashed CSS classes. Click through every page,
  // merging by URL (a link can repeat across pages in rare cases), pausing
  // with jitter — not machine-speed — between clicks, until the Next
  // button is gone (its testid should flip to "-hidden" the same way the
  // Previous button already does on page 1) or a safety cap is hit.
  var MAX_PAGES = 50;
  var allItemsByUrl = {};
  for (var page = 0; page < MAX_PAGES; page++) {
    collectFromCurrentPage().forEach(function (item) {
      allItemsByUrl[item.linkedin_url] = item;
    });

    var nextButton = document.querySelector('[data-testid="pagination-controls-next-button-visible"]');
    if (!nextButton) {
      break; // last page
    }
    nextButton.click();
    await sleep(1200 + Math.random() * 800);
  }

  return Object.values(allItemsByUrl);
}

const btn = document.getElementById("capture-btn");
const statusEl = document.getElementById("status");
const itemsEl = document.getElementById("items");
const metaEl = document.getElementById("meta");

function setStatus(text, kind) {
  statusEl.textContent = text;
  statusEl.className = "status" + (kind ? " " + kind : "");
}

function renderItems(items) {
  if (!items || items.length === 0) {
    itemsEl.style.display = "none";
    itemsEl.innerHTML = "";
    return;
  }
  itemsEl.style.display = "block";
  itemsEl.innerHTML = items
    .map(
      (it) =>
        `<div class="item"><div class="title">${escapeHtml(it.title)}</div>` +
        `<div class="company">${escapeHtml(it.company_name)}${it.location ? " — " + escapeHtml(it.location) : ""}</div></div>`
    )
    .join("");
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s == null ? "" : String(s);
  return div.innerHTML;
}

function renderLastResult(saved) {
  if (!saved) {
    return;
  }
  setStatus(saved.statusText, saved.statusKind);
  renderItems(saved.items);
  if (saved.when) {
    metaEl.textContent = "Last capture: " + new Date(saved.when).toLocaleString();
  }
}

async function restoreLastResult() {
  const { lastResult } = await chrome.storage.local.get("lastResult");
  renderLastResult(lastResult);
}

async function saveResult(statusText, statusKind, items) {
  const record = { statusText, statusKind, items: items || [], when: Date.now() };
  await chrome.storage.local.set({ lastResult: record });
  return record;
}

async function handleCapture() {
  btn.disabled = true;
  setStatus("Reading through every page — this can take a minute or more for a long list…");
  itemsEl.style.display = "none";
  metaEl.textContent = "";

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url || tab.url.indexOf("linkedin.com") === -1) {
      const record = await saveResult("Not on a LinkedIn page — open your Saved Jobs or Applied Jobs list first.", "error", []);
      renderLastResult(record);
      return;
    }

    let items;
    try {
      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: captureLinkedInJobs,
      });
      items = result || [];
    } catch (err) {
      const record = await saveResult("Couldn't read the page: " + (err && err.message ? err.message : err), "error", []);
      renderLastResult(record);
      return;
    }

    if (items.length === 0) {
      const record = await saveResult(
        "Found 0 job cards on this page. Make sure you're on Saved Jobs or Applied Jobs, scrolled so jobs are loaded.",
        "warn",
        []
      );
      renderLastResult(record);
      return;
    }

    setStatus(`Found ${items.length} — sending to Jagir…`);
    try {
      const body = "payload=" + encodeURIComponent(JSON.stringify(items));
      const response = await fetch(CAPTURE_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body,
      });
      if (response.ok) {
        const record = await saveResult(`Sent ${items.length} job(s) to Jagir.`, "ok", items);
        renderLastResult(record);
      } else {
        const record = await saveResult(`Jagir responded with an error (HTTP ${response.status}).`, "error", items);
        renderLastResult(record);
      }
    } catch (err) {
      const record = await saveResult(
        "Couldn't reach Jagir at localhost:8080 — is the app running? (" + (err && err.message ? err.message : err) + ")",
        "error",
        items
      );
      renderLastResult(record);
    }
  } finally {
    btn.disabled = false;
  }
}

btn.addEventListener("click", handleCapture);
restoreLastResult();
