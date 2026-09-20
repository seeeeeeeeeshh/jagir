from nicegui import ui

from app.core.enums import RESEARCH_POSITION_TYPES
from app.core.enums import POSITION_TYPE_OPTIONS
from app.ui.pages.opportunity_list_page import render_opportunity_list

NON_RESEARCH_POSITION_TYPES = [p for p in POSITION_TYPE_OPTIONS if p not in RESEARCH_POSITION_TYPES]


def register():
    @ui.page("/applications")
    def applications_page():
        render_opportunity_list(
            "Applications",
            position_types=NON_RESEARCH_POSITION_TYPES,
            exclude_pre_application=True,
            active_path="/applications",
        )
