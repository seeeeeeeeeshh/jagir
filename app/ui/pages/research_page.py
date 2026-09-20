from nicegui import ui

from app.core.enums import RESEARCH_POSITION_TYPES
from app.ui.pages.opportunity_list_page import render_opportunity_list


def register():
    @ui.page("/research")
    def research_page():
        render_opportunity_list("Research", position_types=list(RESEARCH_POSITION_TYPES), active_path="/research")
