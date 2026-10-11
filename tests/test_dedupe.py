from app.models import Job
from app.pipeline.dedupe import dedupe_jobs


def _job(fp: str, title: str) -> Job:
    return Job(fingerprint=fp, title=title, company="Acme", url="https://x/1")


def test_dedupe_keeps_first_occurrence():
    jobs = [_job("li:1", "A"), _job("li:2", "B"), _job("li:1", "A dup")]
    result = dedupe_jobs(jobs)
    assert [j.fingerprint for j in result] == ["li:1", "li:2"]
    assert result[0].title == "A"
