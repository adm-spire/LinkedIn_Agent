import sqlite3

import pytest

from app.config import AppConfig, EmailConfig, SearchConfig
from app.db.database import init_db
from app.db.repository import JobRepository
from app.models import MatchResult, RunCounts
from app.pipeline.normalize import normalize_job
from app.runner import _send_digest


class FakeSender:
    def __init__(self):
        self.calls: list[str] = []

    def send(self, subject, html_body, text_body):
        self.calls.append(subject)
        return "<mid>"


@pytest.fixture()
def repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield JobRepository(conn)
    conn.close()


def _matched_job(repo, n):
    job = normalize_job(
        {"title": f"AI Engineer {n}", "company": "Acme", "url": f"https://x/{n}"}
    )
    job_id, _ = repo.upsert_job(job)
    repo.save_match(job_id, MatchResult(match=True, score=90, reason="ok"))
    return job_id


def _sent_count(repo):
    return repo.conn.execute(
        "SELECT COUNT(*) AS c FROM email_log WHERE email_status = 'sent'"
    ).fetchone()["c"]


def test_send_digest_slices_and_records_only_sent(repo):
    for i in range(5):
        _matched_job(repo, i)
    config = AppConfig(
        search=SearchConfig(queries=["AI Engineer"]),
        email=EmailConfig(max_jobs_in_digest=2),
    )
    sender = FakeSender()
    counts = RunCounts()
    _send_digest(config, repo, sender, counts)
    assert len(sender.calls) == 1
    assert counts.emailed == 2
    assert _sent_count(repo) == 2


def test_send_digest_no_candidates_does_not_send(repo):
    config = AppConfig(search=SearchConfig(queries=["AI Engineer"]))
    sender = FakeSender()
    counts = RunCounts()
    _send_digest(config, repo, sender, counts)
    assert sender.calls == []
    assert counts.emailed == 0
