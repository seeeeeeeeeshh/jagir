from nicegui import ui

from app.api import google_oauth, linkedin_capture
from app.config import settings
from app.core.logging_setup import setup_logging
from app.ui.pages import (
    all_opportunities_page,
    applications_page,
    calendar_page,
    companies_page,
    cycles_page,
    dashboard_page,
    interviews_page,
    networking_page,
    prep_page,
    research_page,
    saved_jobs_page,
    sync_page,
)
from app.ui.pages import application_detail_page
from app.ui.state import get_connection

setup_logging(settings.log_abs_dir, settings.log_level)

# Initialize the DB connection eagerly so migration errors surface at startup,
# not on the first page load.
get_connection()

dashboard_page.register()
cycles_page.register()
all_opportunities_page.register()
applications_page.register()
research_page.register()
saved_jobs_page.register()
application_detail_page.register()
networking_page.register()
interviews_page.register()
prep_page.register()
companies_page.register()
sync_page.register()
calendar_page.register()
linkedin_capture.register()
google_oauth.register()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="Jagir", reload=False, port=8080)
