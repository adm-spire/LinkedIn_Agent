"""Semantic job matching via DeepSeek with graceful failure."""

from __future__ import annotations

import hashlib
import json

from app.config import MatcherConfig, ProfileConfig
from app.llm.deepseek_client import (
    SYSTEM_PROMPT,
    DeepSeekClient,
    FatalLLMError,
    LLMError,
)
from app.logging_setup import get_logger
from app.models import Job, MatchResult

log = get_logger(__name__)


def compute_profile_hash(profile: ProfileConfig, model: str) -> str:
    """Stable hash of everything that changes a matching decision.

    Stored on each match row; when the hash changes (profile or model edited)
    `get_unmatched_jobs` re-scores the affected jobs automatically.
    """
    payload = {
        "system_prompt": SYSTEM_PROMPT,
        "profile": profile.model_dump(),
        "model": model,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class JobMatcher:
    def __init__(
        self,
        client: DeepSeekClient,
        profile: ProfileConfig,
        config: MatcherConfig,
    ) -> None:
        self.client = client
        self.profile = profile
        self.config = config

    def evaluate(self, job: Job) -> MatchResult | None:
        """Return a validated match result, or None if evaluation failed.

        - disabled matcher          -> None (nothing is stored)
        - FatalLLMError             -> re-raised so the runner aborts matching
        - ordinary LLMError         -> None (job skipped, run continues)
        """
        if not self.config.enabled:
            return None
        try:
            return self.client.match_job(self.profile, job)
        except FatalLLMError:
            log.error("Fatal LLM error on '%s'; aborting matching.", job.title)
            raise
        except LLMError as exc:
            log.error("Matching failed, skipping job '%s': %s", job.title, exc)
            return None
