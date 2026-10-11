from app.browser.session import classify_signals
from app.models import SessionState


def test_authenticated_feed():
    assert classify_signals("https://www.linkedin.com/feed/", "global-nav") is SessionState.AUTHENTICATED


def test_unauthenticated_login_url():
    assert classify_signals("https://www.linkedin.com/login", "") is SessionState.UNAUTHENTICATED


def test_unauthenticated_login_form():
    html = '<form><input id="username"><input id="password"></form>'
    assert classify_signals("https://www.linkedin.com/", html) is SessionState.UNAUTHENTICATED


def test_challenge_url():
    assert classify_signals("https://www.linkedin.com/checkpoint/challenge", "") is SessionState.CHALLENGE


def test_challenge_content():
    assert classify_signals("https://www.linkedin.com/", "please complete security verification") is SessionState.CHALLENGE


def test_jobs_page_authenticated_by_url():
    assert classify_signals("https://www.linkedin.com/jobs/search/", "") is SessionState.AUTHENTICATED


def test_unknown_state():
    assert classify_signals("https://example.com/", "") is SessionState.UNKNOWN
