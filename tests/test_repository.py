import sqlite3

import pytest

from app.db.database import init_db, migrate_db
from app.db.repository import JobRepository
from app.models import MatchResult, RunCounts, RunStatus
from app.pipeline.normalize import normalize_job


@pytest.fixture()
def repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield JobRepository(conn)
    conn.close()


def _job(title="AI Engineer", url="https://www.linkedin.com/jobs/view/1/"):
    return normalize_job({"title": title, "company": "Acme", "location": "Bangalore", "url": url})


def _count_jobs(repo):
    return repo.conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()["c"]


def test_upsert_new_then_seen(repo):
    job = _job()
    job_id, is_new = repo.upsert_job(job)
    assert is_new
    same_id, is_new_again = repo.upsert_job(job)
    assert not is_new_again
    assert same_id == job_id
    assert _count_jobs(repo) == 1


def test_unmatched_jobs_and_match(repo):
    job_id, _ = repo.upsert_job(_job())
    unmatched = repo.get_unmatched_jobs(10)
    assert [jid for jid, _ in unmatched] == [job_id]
    repo.save_match(job_id, MatchResult(match=True, score=90, reason="ok"))
    assert repo.get_unmatched_jobs(10) == []


def test_email_candidates_exclude_sent(repo):
    job_id, _ = repo.upsert_job(_job())
    repo.save_match(job_id, MatchResult(match=True, score=90, reason="ok"))
    assert len(repo.get_email_candidates(70, 10)) == 1
    repo.record_email(job_id, "sent", "mid")
    assert repo.get_email_candidates(70, 10) == []


def test_email_candidates_respect_min_score(repo):
    job_id, _ = repo.upsert_job(_job())
    repo.save_match(job_id, MatchResult(match=True, score=40, reason="meh"))
    assert repo.get_email_candidates(70, 10) == []


def test_rescore_on_profile_hash_change(repo):
    job_id, _ = repo.upsert_job(_job())
    repo.save_match(job_id, MatchResult(match=True, score=90, reason="ok"), profile_hash="A")
    assert repo.get_unmatched_jobs(10, "A", 3) == []
    changed = repo.get_unmatched_jobs(10, "B", 3)
    assert [jid for jid, _ in changed] == [job_id]


def test_rescore_skips_sent_jobs(repo):
    job_id, _ = repo.upsert_job(_job())
    repo.save_match(job_id, MatchResult(match=True, score=90, reason="ok"), profile_hash="A")
    repo.record_email(job_id, "sent", "mid")
    assert repo.get_unmatched_jobs(10, "B", 3) == []


def test_match_attempts_cap(repo):
    job_id, _ = repo.upsert_job(_job())
    repo.increment_match_attempts(job_id)
    repo.increment_match_attempts(job_id)
    assert [jid for jid, _ in repo.get_unmatched_jobs(10, None, 3)] == [job_id]
    repo.increment_match_attempts(job_id)
    assert repo.get_unmatched_jobs(10, None, 3) == []
    assert [jid for jid, _ in repo.get_unmatched_jobs(10, None, 4)] == [job_id]


def test_fail_stale_runs(repo):
    run_id = repo.start_run()
    assert repo.fail_stale_runs() == 1
    row = repo.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "error"
    assert row["error"] == "interrupted"
    assert row["finished_at"]
    assert repo.fail_stale_runs() == 0


def test_migration_adds_missing_columns():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE jobs (id INTEGER PRIMARY KEY, fingerprint TEXT);
        CREATE TABLE matches (job_id INTEGER PRIMARY KEY, matched INTEGER);
        """
    )
    migrate_db(conn)
    job_cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
    match_cols = {r["name"] for r in conn.execute("PRAGMA table_info(matches)")}
    assert "match_attempts" in job_cols
    assert "profile_hash" in match_cols
    migrate_db(conn)
    conn.close()


def test_run_lifecycle(repo):
    run_id = repo.start_run()
    repo.finish_run(run_id, RunStatus.OK, RunCounts(extracted=3, new_jobs=2))
    row = repo.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "ok"
    assert row["finished_at"]
