"""Job normalization and stable identifier construction."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

from app.models import Job

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")


def normalize_text(value: str | None) -> str:
    """Aggressively normalize text for *comparison* (lowercase, no punctuation)."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = value.lower()
    value = _PUNCT.sub(" ", value)
    return _WS.sub(" ", value).strip()


def clean_text(value: str | None) -> str | None:
    """Tidy whitespace for display/storage; empty values become None."""
    if not value:
        return None
    cleaned = _WS.sub(" ", value).strip()
    return cleaned or None


def make_fingerprint(
    company: str | None,
    title: str | None,
    location: str | None,
) -> str:
    """Build a stable dedupe key from the fields a card exposes.

    Hashes the normalized company + title + location. Never title-only, to avoid
    collapsing genuinely different jobs.
    """
    basis = "|".join(normalize_text(x) for x in (company, title, location))
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]
    return f"h:{digest}"


def normalize_job(raw: dict[str, Any]) -> Job:
    """Turn a raw scraped card dict into a validated :class:`Job`."""
    url = raw.get("url") or ""
    company = clean_text(raw.get("company")) or "Unknown"
    title = clean_text(raw.get("title")) or "Unknown"
    location = clean_text(raw.get("location"))

    # Honour a precomputed fingerprint if the caller supplied one; otherwise
    # derive the deterministic hash of the card fields.
    fingerprint = raw.get("fingerprint") or make_fingerprint(company, title, location)

    return Job(
        fingerprint=fingerprint,
        title=title,
        company=company,
        location=location,
        url=url,
        posted_text=clean_text(raw.get("posted_text")),
    )
