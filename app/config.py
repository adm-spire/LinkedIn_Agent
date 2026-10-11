"""Configuration loading.

Two sources, kept deliberately separate:
- **Behavior** (searches, filters, matcher, browser, runtime, email, scraper)
  comes from ``config/config.yaml`` plus the candidate profile in
  ``config/profile.yaml``. Both are validated into the Pydantic models below.
- **Secrets** (API keys, SMTP password) come only from ``.env`` / environment
  via :class:`Secrets`. They are never written to the YAML files.

Relative runtime paths are resolved from the repository root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"
DEFAULT_PROFILE_PATH = REPO_ROOT / "config" / "profile.yaml"

WORKPLACE_VALUES = ("remote", "hybrid", "onsite")
EXPERIENCE_VALUES = (
    "internship",
    "entry",
    "associate",
    "mid-senior",
    "director",
    "executive",
)


class SearchConfig(BaseModel):
    """User-editable search preferences (config.yaml -> search).

    Invalid or missing values raise a validation error at startup that names
    the offending field.
    """

    model_config = ConfigDict(extra="forbid")

    queries: list[str] = Field(..., min_length=1)
    locations: list[str] = Field(default_factory=lambda: [""])
    posted_within_days: int = Field(default=1, ge=0)
    experience_levels: list[str] = Field(default_factory=list)
    workplace: list[str] = Field(default_factory=list)
    max_pages_per_query: int = Field(default=2, ge=1)
    exclude_companies: list[str] = Field(default_factory=list)
    exclude_title_keywords: list[str] = Field(default_factory=list)

    @field_validator("queries")
    @classmethod
    def _validate_queries(cls, value: list[str]) -> list[str]:
        cleaned = [q.strip() for q in value if q and q.strip()]
        if not cleaned:
            raise ValueError(
                "queries must contain at least one non-empty job title or keyword"
            )
        return cleaned

    @field_validator("experience_levels")
    @classmethod
    def _validate_experience_levels(cls, value: list[str]) -> list[str]:
        cleaned = [v.lower().strip() for v in value if v and v.strip()]
        invalid = [v for v in cleaned if v not in EXPERIENCE_VALUES]
        if invalid:
            raise ValueError(
                f"experience_levels contains invalid value(s) {invalid}; "
                f"allowed values: {list(EXPERIENCE_VALUES)}"
            )
        return cleaned

    @field_validator("workplace")
    @classmethod
    def _validate_workplace(cls, value: list[str]) -> list[str]:
        cleaned = [v.lower().strip() for v in value if v and v.strip()]
        invalid = [v for v in cleaned if v not in WORKPLACE_VALUES]
        if invalid:
            raise ValueError(
                f"workplace contains invalid value(s) {invalid}; "
                f"allowed values: {list(WORKPLACE_VALUES)}"
            )
        return cleaned


class FilterConfig(BaseModel):
    """Deterministic pre-LLM rejection rules."""

    reject_title_patterns: list[str] = Field(default_factory=list)
    reject_seniority: list[str] = Field(default_factory=list)
    allow_location_keywords: list[str] = Field(default_factory=list)


class MatcherConfig(BaseModel):
    """DeepSeek matching behaviour and cost guards."""

    enabled: bool = True
    min_score: int = 70            # jobs below this are never emailed
    max_jobs_per_run: int = 40     # cap on jobs sent to the LLM per run
    max_retries: int = 2           # retries per job on transient failures
    max_match_attempts: int = 3    # give up on a job after this many failures


class BrowserConfig(BaseModel):
    """Playwright (sync backend) behaviour."""

    headless: bool = True
    slow_mo_ms: int = 0
    navigation_timeout_ms: int = 45000
    manual_login_timeout_s: int = 900
    min_delay_s: float = 1.5       # human-like random pacing between actions
    max_delay_s: float = 4.0


class RuntimeConfig(BaseModel):
    """Filesystem paths (relative to the repo root) and log level."""

    database_path: str = "data/jobs.db"
    browser_profile_dir: str = "data/browser_profile"
    log_dir: str = "logs"
    log_level: str = "INFO"
    lock_path: str = "data/.lock"


class EmailConfig(BaseModel):
    """Digest formatting."""

    subject_prefix: str = "[Job Hunter]"
    max_jobs_in_digest: int = 50


class McpConfig(BaseModel):
    """Playwright MCP backend settings, including hard safety budgets."""

    model_config = ConfigDict(extra="forbid")

    command: str = "npx"
    args: list[str] = Field(default_factory=lambda: ["@playwright/mcp@latest"])
    headless: bool = True
    max_steps_per_query: int = Field(default=30, ge=1)
    max_llm_calls_per_query: int = Field(default=30, ge=1)
    max_llm_calls_per_run: int = Field(default=200, ge=1)
    max_tool_calls_per_query: int = Field(default=40, ge=1)
    max_total_tokens_per_run: int = Field(default=500_000, ge=1)
    max_wall_clock_s_per_query: int = Field(default=300, ge=1)
    min_delay_s: float = Field(default=1.5, ge=0)
    max_delay_s: float = Field(default=4.0, ge=0)
    max_snapshot_chars: int = Field(default=60_000, ge=100)


class ProfileConfig(BaseModel):
    """The candidate profile used by the matcher (config/profile.yaml)."""

    education: str = ""
    experience_years: int = 0
    skills: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    notes: str = ""


class AppConfig(BaseModel):
    """The whole validated non-secret configuration for one run."""

    search: SearchConfig  # required: the pipeline needs search criteria
    filters: FilterConfig = Field(default_factory=FilterConfig)
    matcher: MatcherConfig = Field(default_factory=MatcherConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    mcp: McpConfig = Field(default_factory=McpConfig)
    profile: ProfileConfig = Field(default_factory=ProfileConfig)

    # Convenience helpers that resolve the raw path strings to absolute Paths.
    @property
    def database_path(self) -> Path:
        return _resolve(self.runtime.database_path)

    @property
    def browser_profile_dir(self) -> Path:
        return _resolve(self.runtime.browser_profile_dir)

    @property
    def log_dir(self) -> Path:
        return _resolve(self.runtime.log_dir)

    @property
    def lock_path(self) -> Path:
        return _resolve(self.runtime.lock_path)


class Secrets(BaseSettings):
    """Secret values sourced only from the environment / .env."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""


def _resolve(path: str | Path) -> Path:
    """Return an absolute path, treating relative paths as repo-relative."""
    p = Path(path)
    return p if p.is_absolute() else (REPO_ROOT / p)


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file into a dict; a missing file is treated as empty."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    profile_path: Path | str = DEFAULT_PROFILE_PATH,
) -> AppConfig:
    """Load and validate config.yaml + profile.yaml into one AppConfig.

    Invalid or missing values raise a Pydantic ValidationError naming the field,
    so misconfiguration fails fast at startup.
    """
    data = _read_yaml(Path(config_path))
    profile = _read_yaml(Path(profile_path))
    data["profile"] = profile  # profile.yaml is merged under the "profile" key
    return AppConfig.model_validate(data)


def load_secrets() -> Secrets:
    """Load secrets from .env / the environment."""
    return Secrets()
