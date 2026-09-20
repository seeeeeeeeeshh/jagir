from nicegui import ui

from app.ui.pages.opportunity_list_page import render_opportunity_list


def register():
    @ui.page("/")
    def all_opportunities_page():
        render_opportunity_list("All Opportunities", active_path="/")
