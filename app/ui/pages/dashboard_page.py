from nicegui import ui

from app.analytics.dashboard_stats import compute_dashboard_analytics
from app.analytics.derived_fields import application_health, deadline_urgency
from app.core.enums import PRE_APPLICATION_STATUSES, RESEARCH_POSITION_TYPES
from app.ui import theme
from app.ui.layout import page_frame
from app.ui.state import companies_repo, cycles_repo, get_connection, opportunities_repo, sync_runs_repo


def register():
    @ui.page("/dashboard")
    def dashboard_page():
        with page_frame("Dashboard", "/dashboard"):
            view_cycle_id = cycles_repo().view_cycle_id()  # None == all cycles
            view_cycle = cycles_repo().get(view_cycle_id) if view_cycle_id is not None else None
            ui.label(f"Showing: {view_cycle.name if view_cycle else 'All cycles'}").classes(
                "jg-panel-title -mb-3"
            )
            last_runs = sync_runs_repo().list_recent(limit=1)
            with ui.row().classes("w-full items-center justify-between -mb-2"):
                if last_runs:
                    last_run = last_runs[0]
                    run_note = " — some records didn't sync" if last_run.status != "success" else ""
                    ui.label(f"As of last LinkedIn sync: {last_run.started_at}{run_note}").classes(
                        "text-xs text-[color:var(--jg-text-dim)]"
                    )
                else:
                    ui.label("No LinkedIn sync has run yet — counts reflect manually entered data only.").classes(
                        "text-xs text-[color:var(--jg-text-dim)]"
                    )
                ui.link("Sync now", "/sync").classes("text-xs no-underline").style("color:var(--jg-blue);")

            opps = opportunities_repo().list_all(cycle_id=view_cycle_id)
            total = len(opps)
            saved = sum(1 for o in opps if o.status in PRE_APPLICATION_STATUSES)
            applied = sum(1 for o in opps if o.status not in PRE_APPLICATION_STATUSES)
            research = sum(1 for o in opps if o.position_type in RESEARCH_POSITION_TYPES)
            offers = sum(1 for o in opps if o.status in ("Offer", "Accepted"))

            needs_review = [o for o in opps if o.needs_review]
            urgent = [o for o in opps if deadline_urgency(o) == "Critical"]
            needs_action = [o for o in opps if application_health(o) == "Needs action"]

            # -- readout strip: compact tabular counts, not stat cards ------
            with ui.card().classes("w-full q-pa-none"):
                with ui.row().classes("w-full gap-0 flex-wrap"):
                    for label, value in [
                        ("Total", total),
                        ("Saved", saved),
                        ("Applied", applied),
                        ("Research / RA", research),
                        ("Offers", offers),
                    ]:
                        with ui.column().classes("jg-readout").style("flex: 1 1 100px;"):
                            ui.label(str(value)).classes("jg-readout-value")
                            ui.label(label).classes("jg-readout-label")

            if not opps:
                with ui.card().classes("w-full"):
                    ui.label(
                        f"No opportunities in {view_cycle.name} yet. Add one, or sync from LinkedIn, to see your pipeline here."
                        if view_cycle
                        else "Add your first opportunity to see your pipeline here."
                    ).classes(
                        "text-[color:var(--jg-text-dim)]"
                    )
                return

            # -- needs attention: given visual priority over raw totals -----
            with ui.card().classes("w-full"):
                ui.label("Needs attention").classes("jg-panel-title")
                if not (urgent or needs_action or needs_review):
                    ui.label("Nothing needs attention right now.").classes(
                        "text-sm text-[color:var(--jg-text-dim)] mt-2"
                    )
                else:
                    companies_by_id = {c.id: c for c in companies_repo().list_all()}
                    seen_ids: set[int] = set()
                    for o, reason in (
                        [(o, "Deadline critical") for o in urgent]
                        + [(o, "Needs action") for o in needs_action]
                        + [(o, "Possible duplicate") for o in needs_review]
                    ):
                        if o.id in seen_ids:
                            continue
                        seen_ids.add(o.id)
                        company = companies_by_id.get(o.company_id)
                        with ui.row().classes("w-full items-center justify-between py-1").style(
                            "border-top: 1px solid var(--jg-border);"
                        ):
                            with ui.row().classes("items-center gap-3"):
                                theme.badge(reason, "attention")
                                ui.link(
                                    f"{o.title} — {company.name if company else 'Unknown'}",
                                    f"/opportunity/{o.id}",
                                ).classes("no-underline text-sm").style("color:var(--jg-text);")
                            ui.label(o.status).classes("text-xs text-[color:var(--jg-text-dim)]")

            analytics = compute_dashboard_analytics(get_connection(), cycle_id=view_cycle_id)

            with ui.row().classes("w-full gap-5 items-start flex-wrap"):
                # -- funnel: current-stage distribution, one hue ------------
                with ui.card().classes("flex-1 min-w-[280px]"):
                    ui.label("Pipeline by stage").classes("jg-panel-title")
                    ui.label("Where active opportunities currently stand — not a historical funnel.").classes(
                        "text-xs text-[color:var(--jg-text-dim)] mt-1 mb-2"
                    )
                    funnel_max = max((s.count for s in analytics.funnel), default=0)
                    for stage in analytics.funnel:
                        theme.bar_row(stage.label, stage.count, funnel_max)

                # -- outcomes: status-colored, matches badge categories -----
                with ui.card().classes("flex-1 min-w-[220px]"):
                    ui.label("Outcomes").classes("jg-panel-title")
                    ui.label("Closed or paused, regardless of current pipeline.").classes(
                        "text-xs text-[color:var(--jg-text-dim)] mt-1 mb-2"
                    )
                    outcome_max = max((s.count for s in analytics.outcomes), default=0)
                    for stage in analytics.outcomes:
                        color = theme.category_color(theme.status_category(stage.label))
                        theme.bar_row(stage.label, stage.count, outcome_max, color=color)

            with ui.row().classes("w-full gap-5 items-start flex-wrap"):
                # -- time to response: a stat tile, not a chart -------------
                with ui.card().classes("flex-1 min-w-[220px]"):
                    ui.label("Time to first interview").classes("jg-panel-title")
                    ttr = analytics.time_to_response
                    if ttr.sample_size == 0:
                        ui.label("Not enough data yet — needs both a Date Applied and a logged interview.").classes(
                            "text-sm text-[color:var(--jg-text-dim)] mt-2"
                        )
                    else:
                        with ui.row().classes("w-full gap-6 mt-1"):
                            with ui.column().classes("gap-0"):
                                ui.label(f"{ttr.median_days:.0f}d").classes("jg-readout-value")
                                ui.label("Median").classes("jg-readout-label")
                            with ui.column().classes("gap-0"):
                                ui.label(f"{ttr.average_days:.1f}d").classes("jg-readout-value")
                                ui.label("Average").classes("jg-readout-label")
                        ui.label(f"Based on {ttr.sample_size} application(s) with a logged interview date.").classes(
                            "text-xs text-[color:var(--jg-text-dim)] mt-2"
                        )

                # -- by position type ----------------------------------------
                with ui.card().classes("flex-1 min-w-[220px]"):
                    ui.label("By position type").classes("jg-panel-title")
                    if not analytics.by_position_type:
                        ui.label("No opportunities yet.").classes("text-sm text-[color:var(--jg-text-dim)] mt-2")
                    elif len(analytics.by_position_type) == 1:
                        # A single category at 100% is a bar comparing nothing
                        # to nothing — a stat line says the same thing plainly.
                        pt = analytics.by_position_type[0]
                        with ui.row().classes("items-baseline gap-2 mt-1"):
                            ui.label(str(pt.count)).classes("jg-readout-value")
                            ui.label(f"{pt.position_type} ({pt.offers} offer(s))").classes(
                                "text-sm text-[color:var(--jg-text-dim)]"
                            )
                    else:
                        pt_max = max(s.count for s in analytics.by_position_type)
                        for pt in analytics.by_position_type:
                            detail = f"{pt.count} total, {pt.offers} offer(s)"
                            theme.bar_row(pt.position_type, pt.count, pt_max, detail=detail)

            # -- top companies --------------------------------------------------
            with ui.card().classes("w-full"):
                ui.label("Top companies").classes("jg-panel-title")
                if not analytics.by_company:
                    ui.label("No opportunities yet.").classes("text-sm text-[color:var(--jg-text-dim)] mt-2")
                else:
                    company_max = max(s.opportunities for s in analytics.by_company)
                    for c in analytics.by_company:
                        detail = f"{c.applications} applied, {c.interviews} interviewing, {c.offers} offer(s), {c.rejections} rejected"
                        theme.bar_row(c.name, c.opportunities, company_max, detail=detail)
