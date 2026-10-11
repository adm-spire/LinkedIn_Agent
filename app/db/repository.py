"""Repository layer over the SQLite connection.

A job's lifecycle is *derived* from which tables have rows for it, rather than a
status column:

    NEW     -> a row in `jobs`, no row in `matches`
    MATCHED -> a row in `matches` (matched=0 means filtered/rejected)
    EMAILED -> a 'sent' row in `email_log`
    RETRY   -> `jobs.match_attempts` below the configured cap

This class is the only place that talks SQL, keeping the rest of the app free of
query details.
"""

from __future__ import annotations

import json
import sqlite3

from app.models import Job, MatchResult, RunCounts, RunStatus, utcnow_iso


class JobRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # -- jobs ---------------------------------------------------------------
    def upsert_job(self, job: Job) -> tuple[int, bool]:
        """Insert a new job, or just bump ``last_seen_at`` if it already exists.

        Identity is the fingerprint (LinkedIn id, else a company/title/location
        hash). Returns ``(job_id, is_new)`` so the caller can count NEW vs SEEN.
        """
        row = self.conn.execute(
            "SELECT id FROM jobs WHERE fingerprint = ?", (job.fingerprint,)
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE jobs SET last_seen_at = ? WHERE id = ?",
                (utcnow_iso(), row["id"]),
            )
            self.conn.commit()
            return row["id"], False

        cur = self.conn.execute(
            """
            INSERT INTO jobs (
                fingerprint, title, company, location, url, posted_text,
                discovered_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.fingerprint,
                job.title,
                job.company,
                job.location,
                job.url,
                job.posted_text,
                job.discovered_at,
                job.last_seen_at,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid), True

    def increment_match_attempts(self, job_id: int) -> None:
        """Record one failed LLM attempt so the job is eventually given up on."""
        self.conn.execute(
            "UPDATE jobs SET match_attempts = match_attempts + 1 WHERE id = ?",
            (job_id,),
        )
        self.conn.commit()

    def get_unmatched_jobs(
        self,
        limit: int,
        profile_hash: str | None = None,
        max_attempts: int = 3,
    ) -> list[tuple[int, Job]]:
        """Jobs that still need (re-)matching, oldest first.

        A job qualifies when:
        - it has no match row yet, OR its stored ``profile_hash`` differs from
          the current one (the candidate profile/model changed), AND
        - it has failed fewer than ``max_attempts`` times, AND
        - it has not already been emailed (a 'sent' row in email_log).
        """
        rows = self.conn.execute(
            """
            SELECT j.* FROM jobs j
            LEFT JOIN matches m ON m.job_id = j.id
            WHERE j.match_attempts < ?
              AND (m.job_id IS NULL OR m.profile_hash IS NOT ?)
              AND j.id NOT IN (
                  SELECT job_id FROM email_log WHERE email_status = 'sent'
              )
            ORDER BY j.discovered_at ASC
            LIMIT ?
            """,
            (max_attempts, profile_hash, limit),
        ).fetchall()

        # Rebuild each row into the domain model (and keep the DB id alongside).
        results: list[tuple[int, Job]] = []
        for row in rows:
            job = Job(
                fingerprint=row["fingerprint"],
                title=row["title"],
                company=row["company"],
                location=row["location"],
                url=row["url"],
                posted_text=row["posted_text"],
                discovered_at=row["discovered_at"],
                last_seen_at=row["last_seen_at"],
            )
            results.append((int(row["id"]), job))
        return results

    # -- matches ------------------------------------------------------------
    def save_match(
        self,
        job_id: int,
        result: MatchResult,
        profile_hash: str | None = None,
    ) -> None:
        """Insert or replace a job's match result (one row per job).

        ``profile_hash`` records which profile+model produced the match so a
        later profile change can trigger a re-score.
        """
        self.conn.execute(
            """
            INSERT INTO matches (
                job_id, matched, score, reason, matching_skills,
                missing_skills, model, profile_hash, matched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                matched = excluded.matched,
                score = excluded.score,
                reason = excluded.reason,
                matching_skills = excluded.matching_skills,
                missing_skills = excluded.missing_skills,
                model = excluded.model,
                profile_hash = excluded.profile_hash,
                matched_at = excluded.matched_at
            """,
            (
                job_id,
                int(result.match),  # SQLite has no bool; store 0/1
                result.score,
                result.reason,
                json.dumps(result.matching_skills),
                json.dumps(result.missing_skills),
                result.model,
                profile_hash,
                utcnow_iso(),
            ),
        )
        self.conn.commit()

    # -- email --------------------------------------------------------------
    def record_email(self, job_id: int, status: str, message_id: str | None = None) -> None:
        """Append an email_log row ('sent'/'failed') for a job."""
        self.conn.execute(
            "INSERT INTO email_log (job_id, email_status, emailed_at, message_id) VALUES (?, ?, ?, ?)",
            (job_id, status, utcnow_iso(), message_id),
        )
        self.conn.commit()

    def get_email_candidates(self, min_score: int, limit: int) -> list[dict]:
        """Matched, high-scoring jobs that have not been emailed yet, best first."""
        rows = self.conn.execute(
            """
            SELECT j.id, j.title, j.company, j.location, j.url,
                   m.score, m.reason, m.matching_skills, m.missing_skills
            FROM jobs j
            JOIN matches m ON m.job_id = j.id
            WHERE m.matched = 1
              AND m.score >= ?
              AND j.id NOT IN (
                  SELECT job_id FROM email_log WHERE email_status = 'sent'
              )
            ORDER BY m.score DESC
            LIMIT ?
            """,
            (min_score, limit),
        ).fetchall()

        results: list[dict] = []
        for row in rows:
            item = dict(row)
            # Skills were stored as JSON strings; decode them for the digest.
            item["matching_skills"] = json.loads(item["matching_skills"] or "[]")
            item["missing_skills"] = json.loads(item["missing_skills"] or "[]")
            results.append(item)
        return results

    # -- runs ---------------------------------------------------------------
    def fail_stale_runs(self, error: str = "interrupted") -> int:
        """Mark runs left in 'running' (e.g. after a crash) as failed."""
        cur = self.conn.execute(
            "UPDATE runs SET status = ?, finished_at = ?, error = ? WHERE status = ?",
            (RunStatus.ERROR.value, utcnow_iso(), error, RunStatus.RUNNING.value),
        )
        self.conn.commit()
        return cur.rowcount

    def start_run(self) -> int:
        """Open a new run row and return its id."""
        cur = self.conn.execute(
            "INSERT INTO runs (started_at, status) VALUES (?, ?)",
            (utcnow_iso(), RunStatus.RUNNING.value),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(
        self,
        run_id: int,
        status: RunStatus | str,
        counts: RunCounts | None = None,
        error: str | None = None,
    ) -> None:
        """Close out a run with its final status, counters and optional error."""
        status_value = status.value if isinstance(status, RunStatus) else status
        self.conn.execute(
            "UPDATE runs SET finished_at = ?, status = ?, counts_json = ?, error = ? WHERE id = ?",
            (
                utcnow_iso(),
                status_value,
                counts.model_dump_json() if counts else None,
                error,
                run_id,
            ),
        )
        self.conn.commit()
