from nicegui import ui

from app.analytics.derived_fields import application_health, days_since_application, deadline_urgency
from app.core.enums import (
    POSITION_TYPE_OPTIONS,
    PRIORITY_OPTIONS,
    SOURCE_OPTIONS,
    STATUS_OPTIONS,
    TARGET_REACH_SAFETY_OPTIONS,
)
from app.core.models import Opportunity
from app.ui import theme

_BADGE_COLS = {"status", "urgency", "health"}

# Editable inline, directly in the grid, without opening the detail page.
# Company is deliberately excluded — reassigning an opportunity's company
# isn't supported anywhere else in the app either (Excel import, same
# reasoning: it touches company-level stats and needs a real lookup/create,
# not a plain field edit).
_EDITABLE_FIELDS = {
    "title", "position_type", "status", "priority", "target_reach_safety",
    "location", "date_saved", "date_applied", "deadline", "source",
}
_SELECT_EDITOR = {
    "position_type": POSITION_TYPE_OPTIONS,
    "status": STATUS_OPTIONS,
    # Priority and Target/Reach/Safety are optional fields, so a blank
    # option is offered and shown when the cell is genuinely empty; the
    # other three are NOT NULL columns and always have a real value.
    "priority": ["", *PRIORITY_OPTIONS],
    "target_reach_safety": ["", *TARGET_REACH_SAFETY_OPTIONS],
    "source": SOURCE_OPTIONS,
}

COLUMN_DEFS = [
    {
        "colId": "select",
        "headerCheckboxSelection": True,
        "checkboxSelection": True,
        "width": 44,
        "pinned": "left",
        "sortable": False,
        "filter": False,
        "resizable": False,
        "suppressMenu": True,
    },
    {"field": "title", "headerName": "Title", "filter": True, "sortable": True, "flex": 2, "minWidth": 220, "tooltipField": "title"},
    {"field": "company", "headerName": "Company", "filter": True, "sortable": True, "flex": 1, "minWidth": 160, "tooltipField": "company"},
    {"field": "position_type", "headerName": "Type", "filter": True, "minWidth": 100},
    {"field": "status", "headerName": "Status", "filter": True, "sortable": True, "minWidth": 130},
    {"field": "priority", "headerName": "Priority", "filter": True, "minWidth": 100},
    {"field": "target_reach_safety", "headerName": "T/R/S", "filter": True, "minWidth": 90},
    {"field": "location", "headerName": "Location", "filter": True, "minWidth": 140},
    {"field": "date_saved", "headerName": "Date Saved", "cellClass": "jg-mono", "minWidth": 120},
    {"field": "date_applied", "headerName": "Date Applied", "cellClass": "jg-mono", "minWidth": 120},
    {"field": "deadline", "headerName": "Deadline", "cellClass": "jg-mono", "minWidth": 110},
    {"field": "days_since_applied", "headerName": "Days Since Applied", "cellClass": "jg-mono", "minWidth": 90},
    {"field": "urgency", "headerName": "Urgency", "minWidth": 100},
    {"field": "health", "headerName": "Health", "minWidth": 110},
    {"field": "source", "headerName": "Source", "filter": True, "minWidth": 110},
]

for _def in COLUMN_DEFS:
    _field = _def.get("field")
    if _field in _EDITABLE_FIELDS:
        _def["editable"] = True
        if _field in _SELECT_EDITOR:
            _def["cellEditor"] = "agSelectCellEditor"
            _def["cellEditorParams"] = {"values": _SELECT_EDITOR[_field]}

# ag-Grid renders values through a JS template; the badge coloring is
# expressed as a cellStyle function keyed off the derived category so the
# grid stays a single color source with theme.py.
_STATUS_JS_MAP = ", ".join(f'"{k}":"{theme.category_color(v)}"' for k, v in theme._STATUS_CATEGORY.items())
_URGENCY_JS_MAP = ", ".join(f'"{k}":"{theme.category_color(v)}"' for k, v in theme._URGENCY_CATEGORY.items())
_HEALTH_JS_MAP = ", ".join(f'"{k}":"{theme.category_color(v)}"' for k, v in theme._HEALTH_CATEGORY.items())

for _col, _map in (("status", _STATUS_JS_MAP), ("urgency", _URGENCY_JS_MAP), ("health", _HEALTH_JS_MAP)):
    for _def in COLUMN_DEFS:
        if _def.get("field") == _col:
            _def[":cellStyle"] = (
                f"(params) => {{ const m = {{{_map}}}; const c = m[params.value] || '{theme.TEXT_DIM}'; "
                "return { color: c, fontWeight: 600, fontSize: '.78rem' }; }"
            )


# Only shown while viewing "All cycles" - inside a single cycle every row has
# the same value, so the column would just be noise.
_CYCLE_COLUMN_DEF = {"field": "cycle", "headerName": "Cycle", "filter": True, "sortable": True, "minWidth": 120}


def opportunity_rows(opportunities: list[Opportunity], companies_by_id: dict, cycles_by_id: dict | None = None) -> list[dict]:
    cycles_by_id = cycles_by_id or {}
    rows = []
    for o in opportunities:
        company = companies_by_id.get(o.company_id)
        rows.append(
            {
                "id": o.id,
                "title": o.title,
                "company": company.name if company else "",
                "cycle": cycles_by_id[o.cycle_id].name if o.cycle_id in cycles_by_id else "",
                "position_type": o.position_type,
                "status": o.status,
                "priority": o.priority or "",
                "target_reach_safety": o.target_reach_safety or "",
                "location": o.location or "",
                "date_saved": o.date_saved or "",
                "date_applied": o.date_applied or "",
                "deadline": o.application_deadline or "",
                "days_since_applied": days_since_application(o) if o.date_applied else "",
                "urgency": deadline_urgency(o),
                "health": application_health(o),
                "source": o.source,
            }
        )
    return rows


def build_grid(
    opportunities: list[Opportunity],
    companies_by_id: dict,
    on_row_click,
    on_selection_change=None,
    on_cell_edit=None,
    cycles_by_id: dict | None = None,
    show_cycle: bool = False,
):
    column_defs = list(COLUMN_DEFS)
    if show_cycle:
        column_defs.insert(3, _CYCLE_COLUMN_DEF)  # right after Company
    grid = ui.aggrid(
        {
            "columnDefs": column_defs,
            "rowData": opportunity_rows(opportunities, companies_by_id, cycles_by_id),
            "enableBrowserTooltips": True,  # native title-attribute tooltips — simplest reliable option for truncated cells
            "rowSelection": "multiple",
            "suppressRowClickSelection": True,  # selection only via the checkbox column, not any cell click
            "singleClickEdit": True,  # editing without opening the detail page is the whole point — one click, not two
            "stopEditingWhenCellsLoseFocus": True,
            # ag-Grid's select editor only enters edit mode on that first
            # click — its dropdown popup still needs a second click to
            # actually expand, which read as "why do I have to click twice".
            # Auto-opening the picker the instant editing starts collapses
            # that into one motion: click a cell, see the options immediately.
            # A plain el.click() doesn't do it — the picker listens for a
            # real mousedown, which .click() alone never dispatches.
            ":onCellEditingStarted": (
                "(params) => setTimeout(() => {"
                " const el = document.querySelector('.ag-cell-inline-editing .ag-picker-field-wrapper');"
                " if (!el) return;"
                " ['mousedown', 'mouseup', 'click'].forEach(type =>"
                "   el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}))"
                " );"
                " }, 30)"
            ),
            "pagination": True,
            "paginationPageSize": 25,
            "domLayout": "autoHeight",
        }
    ).classes("w-full ag-theme-balham-dark").style(
        # NiceGUI gives every aggrid a fixed 16rem height; with domLayout
        # autoHeight the grid grows past it and spills out of its card.
        "height: auto;"
    )

    async def handle_click(e):
        col_id = e.args.get("colId")
        if col_id == "select" or col_id in _EDITABLE_FIELDS:
            return  # an editable cell handles its own click (starts editing); only non-editable cells navigate
        on_row_click(e.args["data"]["id"])

    async def handle_cell_edit(e):
        if on_cell_edit is None:
            return
        # colDef itself isn't part of the serialized event payload sent to
        # Python (only JSON-safe fields survive the bridge) — colId is,
        # same as handle_click above already relies on.
        field = e.args["colId"]
        opportunity_id = e.args["data"]["id"]
        new_value = e.args["newValue"]
        await on_cell_edit(opportunity_id, field, new_value)

    grid.on("cellClicked", handle_click)
    grid.on("cellValueChanged", handle_cell_edit)
    if on_selection_change:
        grid.on("selectionChanged", on_selection_change)
    return grid
