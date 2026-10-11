"""Scraper interface and factory.

The project uses a single scraping backend: the Playwright MCP agent
(:class:`~app.browser.mcp_scraper.McpScraper`). :class:`JobScraper` documents the
contract the orchestrator relies on and :func:`build_scraper` hides the (heavy)
MCP/agent imports behind a lazy import.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.config import AppConfig, Secrets


class JobScraper(Protocol):
    """Common interface implemented by the scraper backend."""

    def collect(self) -> list[dict[str, Any]]:
        """Return raw job-card dicts, ready for ``normalize_job``."""

    def close(self) -> None:
        """Release any resources held for the run."""


def build_scraper(config: AppConfig, secrets: Secrets) -> JobScraper:
    """Create the MCP scraper.

    The import is deferred so importing the app does not pull in the
    MCP/agent stack until a run actually needs it.
    """
    from app.browser.mcp_scraper import McpScraper

    return McpScraper(config, secrets)
