"""Core domain models shared across the application."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 string (used for all DB timestamps)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SessionState(str, Enum):
    """Result of classifying the LinkedIn session (see browser/session.py)."""

    AUTHENTICATED = "authenticated"
    UNAUTHENTICATED = "unauthenticated"
    CHALLENGE = "challenge"
    UNKNOWN = "unknown"


class RunStatus(str, Enum):
    """Lifecycle/terminal states stored in the `runs` table."""

    RUNNING = "running"
    OK = "ok"
    PARTIAL = "partial"          # finished, but some jobs failed to match
    AUTH_REQUIRED = "auth_required"
    ERROR = "error"


class Job(BaseModel):
    """A single job card, normalized from a scraped accessibility snapshot.

    Only the fields a card exposes are modelled; there are no description/detail
    fields because the MCP snapshot does not provide them.
    """

    fingerprint: str  # dedupe key: "h:<sha256 of company|title|location>"
    title: str
    company: str
    location: str | None = None
    url: str
    posted_text: str | None = None
    discovered_at: str = Field(default_factory=utcnow_iso)
    last_seen_at: str = Field(default_factory=utcnow_iso)


class MatchResult(BaseModel):
    """Validated DeepSeek assessment for one job (the LLM output schema)."""

    match: bool
    score: int = Field(ge=0, le=100)
    reason: str = ""
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    model: str = ""


class RunCounts(BaseModel):
    """Per-run counters, stored as JSON in the `runs` table and logged."""

    extracted: int = 0
    duplicates: int = 0
    new_jobs: int = 0
    filtered_out: int = 0
    sent_to_llm: int = 0
    accepted: int = 0
    rejected: int = 0
    llm_errors: int = 0
    emailed: int = 0
