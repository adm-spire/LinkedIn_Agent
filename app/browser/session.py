"""LinkedIn authentication state classification.

Uses multiple signals (URL + page content) and fails safe to UNKNOWN.
The goal is to detect state, never to bypass authentication or security checks.
"""

from __future__ import annotations

import time

from app.logging_setup import get_logger
from app.models import SessionState

log = get_logger(__name__)

LOGIN_PATH_MARKERS = (
    "/login",
    "/uas/login",
    "/signup",
    "authwall",
    "/checkpoint/lg/login",
    "/checkpoint/lg/sign-in",
)

CHALLENGE_PATH_MARKERS = (
    "/checkpoint/challenge",
    "/checkpoint/rp",
    "/checkpoint/lg/add",
    "captcha",
    "/pin/",
)

CHALLENGE_CONTENT_MARKERS = (
    "captcha",
    "security verification",
    "unusual activity",
    "quick security check",
    "verify your identity",
)

LOGIN_CONTENT_MARKERS = (
    'id="username"',
    'id="password"',
    'name="session_key"',
    "sign in to linkedin",
    "join linkedin",
    "email or phone",
)

AUTH_CONTENT_MARKERS = (
    "global-nav",
    "data-test-global-nav",
    "feed-identity-module",
    "my network",
    "global-nav__me",
)


def classify_signals(url: str, html: str) -> SessionState:
    """Pure classification from a URL and lowercased page HTML."""
    u = (url or "").lower()
    h = (html or "").lower()

    if any(marker in u for marker in CHALLENGE_PATH_MARKERS):
        return SessionState.CHALLENGE
    if any(marker in u for marker in LOGIN_PATH_MARKERS):
        return SessionState.UNAUTHENTICATED

    if any(marker in h for marker in CHALLENGE_CONTENT_MARKERS):
        return SessionState.CHALLENGE
    if any(marker in h for marker in LOGIN_CONTENT_MARKERS):
        return SessionState.UNAUTHENTICATED
    if any(marker in h for marker in AUTH_CONTENT_MARKERS):
        return SessionState.AUTHENTICATED

    if "/feed" in u or "/jobs" in u or "linkedin.com/in/" in u:
        return SessionState.AUTHENTICATED

    return SessionState.UNKNOWN


def classify(page) -> SessionState:
    """Classify the current page state."""
    url = getattr(page, "url", "") or ""
    try:
        html = page.content()
    except Exception as exc:  # noqa: BLE001 - fail safe
        log.warning("Could not read page content for session classification: %s", exc)
        html = ""
    return classify_signals(url, html)


def wait_for_authentication(page, timeout_s: int, poll_s: float = 5.0) -> SessionState:
    """Poll until the page is authenticated or the timeout expires."""
    deadline = time.monotonic() + timeout_s
    last = SessionState.UNKNOWN
    while time.monotonic() < deadline:
        last = classify(page)
        if last is SessionState.AUTHENTICATED:
            return last
        if last is SessionState.CHALLENGE:
            log.warning("Security challenge detected; manual action likely required.")
        time.sleep(poll_s)
    return last
