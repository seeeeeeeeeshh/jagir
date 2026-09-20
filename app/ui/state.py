import sqlite3

from app.config import settings
from app.db.database import init_database
from app.db.repositories.companies_repo import CompaniesRepo
from app.db.repositories.contacts_repo import ContactsRepo
from app.db.repositories.cycles_repo import CyclesRepo
from app.db.repositories.duplicate_candidates_repo import DuplicateCandidatesRepo
from app.db.repositories.interviews_repo import InterviewsRepo
from app.db.repositories.opportunities_repo import OpportunitiesRepo
from app.db.repositories.prep_resources_repo import PrepResourcesRepo
from app.db.repositories.sync_runs_repo import SyncRunsRepo

_conn: sqlite3.Connection | None = None


def get_connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = init_database(settings.database_abs_path)
    return _conn


def opportunities_repo() -> OpportunitiesRepo:
    return OpportunitiesRepo(get_connection())


def companies_repo() -> CompaniesRepo:
    return CompaniesRepo(get_connection())


def cycles_repo() -> CyclesRepo:
    return CyclesRepo(get_connection())


def contacts_repo() -> ContactsRepo:
    return ContactsRepo(get_connection())


def interviews_repo() -> InterviewsRepo:
    return InterviewsRepo(get_connection())


def prep_resources_repo() -> PrepResourcesRepo:
    return PrepResourcesRepo(get_connection())


def sync_runs_repo() -> SyncRunsRepo:
    return SyncRunsRepo(get_connection())


def duplicate_candidates_repo() -> DuplicateCandidatesRepo:
    return DuplicateCandidatesRepo(get_connection())
