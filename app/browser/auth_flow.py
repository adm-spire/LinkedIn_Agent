"""Authentication flow: detect session state and, if needed, prompt manual login."""

from __future__ import annotations

from app.browser.profile import first_page, persistent_context
from app.browser.session import classify, wait_for_authentication
from app.config import AppConfig, Secrets
from app.logging_setup import get_logger
from app.models import SessionState
from app.notify.email_digest import EmailSender

log = get_logger(__name__)

FEED_URL = "https://www.linkedin.com/feed/"
LOGIN_URL = "https://www.linkedin.com/login"


def check_session(config: AppConfig) -> SessionState:
    """Open the saved profile headless, hit /feed, and classify the session."""
    with persistent_context(
        config.browser_profile_dir,
        headless=True,
        navigation_timeout_ms=config.browser.navigation_timeout_ms,
    ) as context:
        page = first_page(context)
        try:
            page.goto(FEED_URL, wait_until="domcontentloaded")
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not reach LinkedIn to check session: %s", exc)
            return SessionState.UNKNOWN
        return classify(page)


def _notify_login_required(config: AppConfig, secrets: Secrets) -> None:
    """Email the user that a manual login is needed (best-effort)."""
    try:
        EmailSender(secrets).send_notification(
            f"{config.email.subject_prefix} LinkedIn login required",
            "The LinkedIn session is not authenticated. A browser window will open; "
            "please log in manually. The next scheduled run can continue once you do.",
        )
    except Exception as exc:  # noqa: BLE001 - notification is best-effort
        log.error("Could not send login-required email: %s", exc)


def ensure_authenticated(config: AppConfig, secrets: Secrets) -> SessionState:
    """Return a usable session state, prompting a headed manual login if needed.

    UNKNOWN states are returned as-is (fail safe -> caller exits, retry next
    cron). UNAUTHENTICATED/CHALLENGE open a visible browser and wait.
    """
    state = check_session(config)
    if state is SessionState.AUTHENTICATED:
        log.info("LinkedIn session is valid.")
        return state

    log.warning("LinkedIn session state: %s", state.value)
    # Anything we cannot act on (e.g. UNKNOWN) is returned unchanged.
    if state not in (SessionState.UNAUTHENTICATED, SessionState.CHALLENGE):
        return state

    _notify_login_required(config, secrets)
    log.info(
        "Opening headed browser for manual login (timeout %ss).",
        config.browser.manual_login_timeout_s,
    )
    try:
        with persistent_context(
            config.browser_profile_dir,
            headless=False,
            slow_mo_ms=config.browser.slow_mo_ms,
            navigation_timeout_ms=config.browser.navigation_timeout_ms,
        ) as context:
            page = first_page(context)
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            return wait_for_authentication(page, config.browser.manual_login_timeout_s)
    except Exception as exc:  # noqa: BLE001 - e.g. no display available under cron
        log.error("Could not open headed browser for manual login: %s", exc)
        return state
