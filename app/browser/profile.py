"""Playwright persistent browser context management.

The dedicated profile at data/browser_profile/ retains the LinkedIn session
between executions. We never touch the user's normal browser profile.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from playwright.sync_api import BrowserContext, Playwright, sync_playwright

DEFAULT_VIEWPORT = {"width": 1366, "height": 900}


def launch_persistent_context(
    playwright: Playwright,
    profile_dir: Path,
    *,
    headless: bool = True,
    slow_mo_ms: int = 0,
    navigation_timeout_ms: int = 45000,
) -> BrowserContext:
    """Open Chromium over the dedicated (login-holding) profile directory."""
    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=headless,
        slow_mo=slow_mo_ms,
        viewport=DEFAULT_VIEWPORT,
        args=["--no-first-run", "--no-default-browser-check"],
    )
    context.set_default_navigation_timeout(navigation_timeout_ms)
    return context


@contextmanager
def persistent_context(
    profile_dir: Path,
    *,
    headless: bool = True,
    slow_mo_ms: int = 0,
    navigation_timeout_ms: int = 45000,
) -> Iterator[BrowserContext]:
    """Yield a persistent context, closing Playwright cleanly on exit."""
    with sync_playwright() as playwright:
        context = launch_persistent_context(
            playwright,
            profile_dir,
            headless=headless,
            slow_mo_ms=slow_mo_ms,
            navigation_timeout_ms=navigation_timeout_ms,
        )
        try:
            yield context
        finally:
            context.close()


def first_page(context: BrowserContext):
    """Return the context's first open page, creating one if there is none."""
    return context.pages[0] if context.pages else context.new_page()
