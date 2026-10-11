from app.config import EmailConfig
from app.notify.email_digest import build_digest

JOBS = [
    {
        "id": 1,
        "title": "AI Engineer <script>",
        "company": "Acme",
        "location": "Bangalore",
        "url": "https://www.linkedin.com/jobs/view/1/",
        "score": 92,
        "reason": "Python + LLM overlap",
        "matching_skills": ["Python", "FastAPI"],
        "missing_skills": ["AWS"],
    }
]


def test_subject_counts_jobs():
    subject, _, _ = build_digest(JOBS, EmailConfig())
    assert subject == "[Job Hunter] 1 New Matching LinkedIn Jobs"


def test_text_contains_details():
    _, _, text = build_digest(JOBS, EmailConfig())
    assert "AI Engineer" in text
    assert "Acme" in text
    assert "92%" in text
    assert "AWS" in text
    assert "https://www.linkedin.com/jobs/view/1/" in text


def test_html_escapes_job_content():
    _, html, _ = build_digest(JOBS, EmailConfig())
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_text_body_uses_raw_values():
    _, _, text = build_digest(JOBS, EmailConfig())
    assert "AI Engineer <script>" in text
    assert "&lt;script&gt;" not in text


def test_build_digest_does_not_truncate():
    jobs = [dict(JOBS[0], id=i) for i in range(5)]
    subject, _, text = build_digest(jobs, EmailConfig(max_jobs_in_digest=2))
    assert "5 New Matching" in subject
    assert text.count("Apply:") == 5
