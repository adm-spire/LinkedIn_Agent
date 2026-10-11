"""Deterministic, inexpensive filtering applied before the LLM.

Rejecting a job here costs nothing, so both filters run *before* DeepSeek:
- :class:`ExcludeFilter`  -> user's own company/title exclusions (from `search`).
- :class:`RuleFilter`     -> seniority, disallowed locations (from `filters`).

Each returns a :class:`FilterDecision`; "not allowed" jobs are stored with a
`match=False` row so they are not re-evaluated every run.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.config import FilterConfig
from app.models import Job


class FilterDecision(BaseModel):
    """Outcome of a filter: allowed, or rejected with a human-readable reason."""

    allowed: bool
    reason: str | None = None


class RuleFilter:
    """Config-driven title/seniority/location rules (from `filters`)."""

    def __init__(self, config: FilterConfig) -> None:
        # Pre-compile regexes once, at construction, not per job.
        self._title_patterns = [re.compile(p, re.IGNORECASE) for p in config.reject_title_patterns]
        self._seniority_patterns = [
            re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
            for word in config.reject_seniority
        ]
        self._location_keywords = [k.lower() for k in config.allow_location_keywords]

    def check(self, job: Job) -> FilterDecision:
        title = job.title or ""

        # 1) Explicit title regexes (e.g. "senior|staff|manager").
        for pattern in self._title_patterns:
            if pattern.search(title):
                return FilterDecision(allowed=False, reason=f"title rejected by pattern: {pattern.pattern}")

        # 2) Seniority words on word boundaries (avoids matching substrings).
        for pattern in self._seniority_patterns:
            if pattern.search(title):
                return FilterDecision(allowed=False, reason=f"seniority mismatch: {pattern.pattern}")

        # 3) Location allow-list; only applies when both are present.
        if job.location and self._location_keywords:
            location = job.location.lower()
            if not any(keyword in location for keyword in self._location_keywords):
                return FilterDecision(allowed=False, reason=f"location not allowed: {job.location}")

        return FilterDecision(allowed=True)


class ExcludeFilter:
    """User-defined company/title exclusions (from the `search` section).

    Matching is case-insensitive substring, so "acme" excludes "Acme Corp".
    """

    def __init__(self, companies: list[str], title_keywords: list[str]) -> None:
        self._companies = [c.strip().lower() for c in companies if c and c.strip()]
        self._title_keywords = [
            k.strip().lower() for k in title_keywords if k and k.strip()
        ]

    def check(self, job: Job) -> FilterDecision:
        company = (job.company or "").lower()
        for name in self._companies:
            if name == company or name in company:
                return FilterDecision(
                    allowed=False, reason=f"excluded company: {job.company}"
                )

        title = (job.title or "").lower()
        for keyword in self._title_keywords:
            if keyword in title:
                return FilterDecision(
                    allowed=False, reason=f"excluded title keyword: {keyword}"
                )

        return FilterDecision(allowed=True)
