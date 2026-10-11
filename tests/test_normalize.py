from app.pipeline.normalize import make_fingerprint, normalize_job, normalize_text


def test_normalize_text_collapses_and_strips_punctuation():
    assert normalize_text("  Acme,  Inc.  ") == "acme inc"


def test_fingerprint_is_deterministic_and_normalized():
    a = make_fingerprint("Acme Inc", "AI Engineer", "Bangalore")
    b = make_fingerprint("acme, inc", "ai  engineer", "bangalore")
    assert a == b
    assert a.startswith("h:")


def test_normalize_job_from_card():
    job = normalize_job(
        {
            "title": "  AI Engineer ",
            "company": "Acme",
            "location": "Bangalore (On-site)",
            "url": "https://www.linkedin.com/jobs/search/?keywords=ai",
        }
    )
    assert job.title == "AI Engineer"
    assert job.company == "Acme"
    assert job.location == "Bangalore (On-site)"
    assert job.fingerprint.startswith("h:")  # no job id -> hash fingerprint
