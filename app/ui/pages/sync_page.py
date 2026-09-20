from nicegui import run, ui

from app.config import settings
from app.sync.bookmarklet_js import bookmarklet_href
from app.sync.sync_orchestrator import run_sync
from app.ui import theme
from app.ui.components.duplicate_review_panel import render_duplicate_review_panel
from app.ui.layout import page_frame
from app.ui.state import get_connection, sync_runs_repo


def register():
    @ui.page("/sync")
    def sync_page():
        with page_frame("Sync", "/sync", show_data_actions=False):

            @ui.refreshable
            def runs_panel():
                ui.label("Recent sync runs").classes("jg-panel-title")
                runs = sync_runs_repo().list_recent()
                if not runs:
                    ui.label("No syncs have run yet.").classes("text-sm text-[color:var(--jg-text-dim)] mt-2")
                for sync_run in runs:
                    with ui.card().classes("w-full"):
                        with ui.row().classes("items-center gap-3"):
                            ui.label(f"{sync_run.started_at}").classes("jg-mono text-sm")
                            run_status_category = {
                                "success": "positive",
                                "partial": "attention",
                                "failed": "negative",
                            }.get(sync_run.status, "pending")
                            theme.badge(sync_run.status, run_status_category)
                        if sync_run.summary_text:
                            ui.label(sync_run.summary_text).classes("text-sm text-[color:var(--jg-text-dim)] mt-1")

            dup_panel = render_duplicate_review_panel()

            # -- primary flow: Chrome extension, runs inside the user's own -
            # -- already-logged-in LinkedIn tab, no cookies/credentials -----
            # -- ever leave the browser ---------------------------------------
            with ui.card().classes("w-full"):
                ui.label("Capture from LinkedIn").classes("jg-panel-title")
                ui.label(
                    "One-time setup: open chrome://extensions, enable Developer mode (top right), "
                    "click \"Load unpacked\", and select this project's extension/ folder."
                ).classes("text-[color:var(--jg-text-dim)] mt-2")
                ui.label(
                    "Then: while viewing your LinkedIn Saved Jobs or Applied Jobs list (scrolled "
                    "so the jobs you want are loaded), click the Jagir toolbar icon and press "
                    "\"Capture from this page\" in the popup. It reads the page you're already "
                    "looking at and sends the jobs here — nothing runs in the background, no "
                    "cookies or credentials ever leave your browser, and nothing happens until you "
                    "click the button. The popup shows exactly what it found (or what went wrong)."
                ).classes("text-[color:var(--jg-text-dim)] mt-2")
                ui.label(
                    "Only captures what's already rendered on the page — no detail-page fields "
                    "(salary, description) yet, and its selectors are a best-effort starting point "
                    "(extension/popup.js) you may need to adjust if LinkedIn's markup has "
                    "changed since a capture shows 0."
                ).classes("text-xs text-[color:var(--jg-text-dim)] mt-3")

            # -- fallback: bookmarklet, same idea without installing an -----
            # -- extension ---------------------------------------------------
            with ui.expansion("No extension? Use a bookmarklet instead").classes("w-full"):
                ui.label(
                    "Same idea as the extension above (runs in your own LinkedIn tab, captures "
                    "only what's rendered, nothing automatic) but as a plain bookmark instead of "
                    "an installed extension — a bit more friction, nothing to load unpacked."
                ).classes("text-[color:var(--jg-text-dim)]")

                ui.html(
                    f'<a href="{bookmarklet_href()}" '
                    'style="display:inline-block;margin-top:.75rem;padding:.5rem 1rem;'
                    'background:var(--jg-panel-raised);border:1px solid var(--jg-blue);'
                    'border-radius:4px;color:var(--jg-blue);font-size:.85rem;font-weight:600;'
                    'text-decoration:none;cursor:grab;">📎 Capture LinkedIn Jobs</a>',
                    sanitize=False,  # a javascript: bookmarklet href — DOMPurify strips this by
                                      # default (correctly, for untrusted input); this content is
                                      # server-generated from our own source, not user input.
                )
                ui.label("Drag it to your bookmarks bar, then click it from a LinkedIn jobs list.").classes(
                    "text-xs text-[color:var(--jg-text-dim)] mt-2"
                )

            # -- advanced: the original Playwright-automation path ----------
            with ui.expansion("Advanced: automated browser sync").classes("w-full"):
                ui.label(
                    "Drives a separate, automated browser through your own LinkedIn session instead "
                    "of using a tab you're already in. More complete (visits both list pages and "
                    "job detail pages on its own) but requires a headed browser window and running "
                    "the app from your own terminal (not through a remote/automated session) for the "
                    "login step to actually display."
                ).classes("text-[color:var(--jg-text-dim)]")

                async def start_sync():
                    # run_sync executes on a plain worker thread (nicegui.run.io_bound)
                    # with no client/slot context, so its on_progress callback can only
                    # safely log — it must not touch UI elements directly. We show a
                    # static "in progress" label instead of live per-step text.
                    sync_button.props("disable")
                    status_label.set_text("Sync in progress — this can take a minute…")

                    sync_run = await run.io_bound(run_sync, get_connection(), settings)

                    # The user may have navigated away or closed the tab during
                    # the (potentially 30s+) sync — updating a disconnected
                    # client's UI raises RuntimeError, which is expected here,
                    # not a bug to surface.
                    try:
                        if sync_run is not None:
                            ui.notify(
                                sync_run.summary_text or sync_run.status,
                                type="positive" if sync_run.status == "success" else "warning",
                            )
                        sync_button.props(remove="disable")
                        status_label.set_text("")
                        runs_panel.refresh()
                        dup_panel.refresh()
                    except RuntimeError:
                        pass

                sync_button = ui.button("Sync LinkedIn (automated)", on_click=start_sync).props("outline").classes("mt-3")
                status_label = ui.label("").classes("text-sm text-[color:var(--jg-text-dim)] mt-2")

            runs_panel()
