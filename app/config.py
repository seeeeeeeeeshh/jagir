from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_path: str = "data/job_tracker.db"
    browser_profile_dir: str = "data/browser_profile"
    browser_headless: bool = False
    keep_browser_open: bool = False

    raw_snapshot_mode: Literal["errors_and_debug", "every_sync", "none"] = "errors_and_debug"
    raw_snapshot_retention_days: int = 14

    # Kept deliberately low, with randomized pacing between actions
    # (action_delay_*), so a sync looks and behaves like occasional manual
    # browsing rather than a scraper hammering the site.
    max_items_per_list: int = 25
    max_detail_fetches_per_run: int = 8
    action_delay_min_seconds: float = 1.5
    action_delay_max_seconds: float = 4.0

    log_level: str = "INFO"
    log_dir: str = "data/logs"

    # Google Calendar (see README's "Google Calendar" section for setup).
    # The refresh token lives in its own local file, not the sqlite db, for
    # the same reason browser_profile_dir is separate — so "copy the db to
    # back it up" never silently carries a live credential along with it.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8080/oauth/google/callback"
    google_token_path: str = "data/google_token.json"

    @property
    def database_abs_path(self) -> Path:
        p = Path(self.database_path)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def browser_profile_abs_dir(self) -> Path:
        p = Path(self.browser_profile_dir)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def google_token_abs_path(self) -> Path:
        p = Path(self.google_token_path)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def google_calendar_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def log_abs_dir(self) -> Path:
        p = Path(self.log_dir)
        return p if p.is_absolute() else PROJECT_ROOT / p


settings = Settings()
