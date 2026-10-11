from app.config import FilterConfig
from app.models import Job
from app.pipeline.filters import ExcludeFilter, RuleFilter


def _job(title: str, location: str | None = "Bangalore, India") -> Job:
    return Job(fingerprint="li:1", title=title, company="Acme", location=location, url="https://x/1")


CONFIG = FilterConfig(
    reject_title_patterns=[r"\b(senior|staff|principal|lead|manager|director)\b", r"\bintern\b"],
    reject_seniority=["senior", "staff", "principal", "lead", "manager", "director"],
    allow_location_keywords=["india", "remote", "bangalore"],
)


def test_allows_matching_junior_role():
    assert RuleFilter(CONFIG).check(_job("AI Engineer")).allowed


def test_rejects_senior_titles():
    decision = RuleFilter(CONFIG).check(_job("Senior Software Engineer"))
    assert not decision.allowed


def test_rejects_disallowed_location():
    decision = RuleFilter(CONFIG).check(_job("AI Engineer", "New York"))
    assert not decision.allowed


def test_allows_when_no_location():
    assert RuleFilter(CONFIG).check(_job("AI Engineer", None)).allowed


def test_exclude_company():
    decision = ExcludeFilter(["Acme"], []).check(_job("AI Engineer"))
    assert not decision.allowed


def test_exclude_company_is_case_insensitive():
    decision = ExcludeFilter(["acme"], []).check(_job("AI Engineer"))
    assert not decision.allowed


def test_exclude_title_keyword():
    decision = ExcludeFilter([], ["sales"]).check(_job("Sales Engineer"))
    assert not decision.allowed


def test_exclude_allows_unrelated_job():
    job = Job(fingerprint="li:2", title="AI Engineer", company="Other", url="https://x/2")
    assert ExcludeFilter(["Acme"], ["sales"]).check(job).allowed
