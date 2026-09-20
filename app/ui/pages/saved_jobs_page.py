from nicegui import ui

from app.core.enums import PRE_APPLICATION_STATUSES
from app.ui.pages.opportunity_list_page import render_opportunity_list


def register():
    @ui.page("/saved-jobs")
    def saved_jobs_page():
        render_opportunity_list("Saved Jobs", statuses=list(PRE_APPLICATION_STATUSES), active_path="/saved-jobs")
