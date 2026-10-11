"""Build LinkedIn job search URLs from user search preferences.

No request is made here; this module only constructs URLs. One URL is produced
per (query, location) pair. Pacing and navigation limits are enforced by the
extraction layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

from app.config import SearchConfig

BASE_URL = "https://www.linkedin.com/jobs/search/"

# LinkedIn encodes these filters as short numeric codes in the query string.
# Multiple values are comma-joined (e.g. f_WT=2,3 for remote + hybrid).
EXPERIENCE_CODES = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid-senior": "4",
    "director": "5",
    "executive": "6",
}

WORKPLACE_CODES = {
    "onsite": "1",
    "remote": "2",
    "hybrid": "3",
}

RESULTS_PER_PAGE = 25


@dataclass(frozen=True)
class SearchParams:
    """A single resolved search: one query for one location."""

    query: str
    location: str
    posted_within_days: int | None
    workplace: tuple[str, ...]
    experience_levels: tuple[str, ...]
    max_pages: int
    max_results: int


def expand_searches(search: SearchConfig) -> list[SearchParams]:
    """Expand the config into one SearchParams per (query, location) pair.

    e.g. 3 queries x 2 locations => 6 searches, each paginated independently.
    """
    posted = search.posted_within_days or None
    max_results = search.max_pages_per_query * RESULTS_PER_PAGE
    return [
        SearchParams(
            query=query,
            location=location,
            posted_within_days=posted,
            workplace=tuple(search.workplace),
            experience_levels=tuple(search.experience_levels),
            max_pages=search.max_pages_per_query,
            max_results=max_results,
        )
        for query in search.queries
        for location in search.locations
    ]


def _code_list(values: tuple[str, ...], mapping: dict[str, str]) -> str | None:
    """Map filter values to LinkedIn codes and comma-join them (or None)."""
    codes = [mapping[v] for v in values if v in mapping]
    return ",".join(codes) if codes else None


def build_search_url(params: SearchParams, page_index: int = 0) -> str:
    """Build the LinkedIn jobs search URL for one resolved search + page."""
    parts: list[str] = [f"keywords={quote_plus(params.query)}"]
    if params.location:
        parts.append(f"location={quote_plus(params.location)}")
    if params.posted_within_days:
        parts.append(f"f_TPR=r{int(params.posted_within_days) * 86400}")
    workplace = _code_list(params.workplace, WORKPLACE_CODES)
    if workplace:
        parts.append(f"f_WT={workplace}")
    experience = _code_list(params.experience_levels, EXPERIENCE_CODES)
    if experience:
        parts.append(f"f_E={experience}")
    if page_index:
        parts.append(f"start={page_index * RESULTS_PER_PAGE}")
    return BASE_URL + "?" + "&".join(parts)
