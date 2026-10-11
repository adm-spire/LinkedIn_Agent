"""In-memory deduplication by fingerprint."""

from __future__ import annotations

from app.models import Job


def dedupe_jobs(jobs: list[Job]) -> list[Job]:
    """Drop duplicate fingerprints (same job found by several searches).

    Keeps the first occurrence so ordering by discovery time is preserved.
    """
    seen: set[str] = set()
    unique: list[Job] = []
    for job in jobs:
        if job.fingerprint in seen:
            continue
        seen.add(job.fingerprint)
        unique.append(job)
    return unique
