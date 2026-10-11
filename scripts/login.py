"""First-time / interactive LinkedIn login helper.

Launches the dedicated persistent profile in headed mode so the user can log in
manually (including any MFA LinkedIn requires). The session is retained in
data/browser_profile/ for future headless cron runs.

Usage:
    .venv/bin/python scripts/login.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.browser.profile import first_page, persistent_context  # noqa: E402
from app.browser.session import classify, wait_for_authentication  # noqa: E402
from app.config import load_config  # noqa: E402
from app.logging_setup import get_logger, setup_logging  # noqa: E402
from app.models import SessionState  # noqa: E402


def main() -> int:
    config = load_config()
    setup_logging(config.log_dir, config.runtime.log_level)
    log = get_logger("login")

    log.info("Opening LinkedIn in a headed browser for manual login...")
    with persistent_context(
        config.browser_profile_dir,
        headless=False,
        slow_mo_ms=config.browser.slow_mo_ms,
        navigation_timeout_ms=config.browser.navigation_timeout_ms,
    ) as context:
        page = first_page(context)
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        print("\nA browser window has opened.")
        print("Log in to LinkedIn manually (handle MFA if prompted).")
        print("This window will close automatically once the session is valid.\n")

        state = wait_for_authentication(
            page,
            timeout_s=config.browser.manual_login_timeout_s,
        )
        if state is SessionState.AUTHENTICATED:
            log.info("Login successful. Session saved to %s", config.browser_profile_dir)
            print("Login successful. Session saved. You can now run `python -m app`.")
            return 0

        log.error("Login not completed (final state: %s).", state.value)
        print(f"Login not completed (state: {state.value}). Run the script again.")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
