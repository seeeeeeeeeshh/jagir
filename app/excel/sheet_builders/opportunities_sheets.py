import sqlite3

import pandas as pd

from app.core.enums import PRE_APPLICATION_STATUSES, RESEARCH_POSITION_TYPES
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.excel.sheet_builders.opportunity_rows import opportunities_to_dataframe

NON_RESEARCH_POSITION_TYPES = ["Internship", "FullTime", "PartTime", "Other"]


def _companies_by_id(conn: sqlite3.Connection) -> dict:
    return {c.id: c for c in CompaniesRepo(conn).list_all()}


def build_all_opportunities(conn: sqlite3.Connection) -> pd.DataFrame:
    opps = OpportunitiesRepo(conn).list_all()
    return opportunities_to_dataframe(conn, opps, _companies_by_id(conn))


def build_applications(conn: sqlite3.Connection) -> pd.DataFrame:
    opps = OpportunitiesRepo(conn).list_all(
        position_types=NON_RESEARCH_POSITION_TYPES, exclude_pre_application=True
    )
    return opportunities_to_dataframe(conn, opps, _companies_by_id(conn))


def build_research(conn: sqlite3.Connection) -> pd.DataFrame:
    opps = OpportunitiesRepo(conn).list_all(position_types=list(RESEARCH_POSITION_TYPES))
    return opportunities_to_dataframe(conn, opps, _companies_by_id(conn))


def build_saved_jobs(conn: sqlite3.Connection) -> pd.DataFrame:
    opps = OpportunitiesRepo(conn).list_all(statuses=list(PRE_APPLICATION_STATUSES))
    return opportunities_to_dataframe(conn, opps, _companies_by_id(conn))
