"""End-to-end run orchestration.

`run()` is the single entry point that wires the pipeline together:

    authenticate -> collect jobs -> store/dedupe -> rule-filter
    -> DeepSeek match -> email digest

Each step is a small helper below so the flow reads top-to-bottom. Errors are
isolated per job wherever possible (`filters.py`, `matcher.py`); only a
`FatalLLMError` or a `LoginWallError` aborts the whole run.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.browser.auth_flow import ensure_authenticated
from app.browser.guards import LoginWallError
from app.browser.scraper import JobScraper, build_scraper
from app.config import AppConfig, Secrets
from app.db.repository import JobRepository
from app.llm.deepseek_client import DeepSeekClient, FatalLLMError
from app.logging_setup import get_logger
from app.models import MatchResult, RunCounts, RunStatus, SessionState
from app.notify.email_digest import EmailSender, build_digest
from app.pipeline.dedupe import dedupe_jobs
from app.pipeline.filters import ExcludeFilter, RuleFilter
from app.pipeline.matcher import JobMatcher, compute_profile_hash
from app.pipeline.normalize import normalize_job

log = get_logger(__name__)

# Process exit codes, also documented in the README / final_plan.
EXIT_OK = 0
EXIT_FATAL = 1
EXIT_PARTIAL = 2
EXIT_AUTH_REQUIRED = 3
EXIT_LOCKED = 4


@dataclass
class RunResult:
    """What a single run achieved: its status, counters and process exit code."""

    status: RunStatus
    counts: RunCounts
    exit_code: int


def _collect_new_jobs(
    scraper: JobScraper, config: AppConfig, repo: JobRepository, counts: RunCounts
) -> None:
    """Scrape, normalize, dedupe and store jobs. New vs. seen is derived from
    whether the fingerprint already existed (no status column)."""
    cards = scraper.collect()
    counts.extracted += len(cards)

    # Normalize raw cards into the Job model, then drop duplicates that appeared
    # across the different (query x location) searches.
    jobs = dedupe_jobs([normalize_job(card) for card in cards])

    for job in jobs:
        _job_id, is_new = repo.upsert_job(job)
        if is_new:
            counts.new_jobs += 1
        else:
            counts.duplicates += 1


def _match_jobs(
    config: AppConfig,
    repo: JobRepository,
    matcher: JobMatcher,
    rule_filter: RuleFilter,
    exclude_filter: ExcludeFilter,
    counts: RunCounts,
    profile_hash: str,
) -> None:
    """Score every candidate job against the profile with DeepSeek.

    Two cheap, LLM-free filters run first (user exclusions, then rule filter) so
    rejected jobs cost nothing. `profile_hash` is stored with each match so that
    a profile change later re-scores the job automatically.
    """
    candidates = repo.get_unmatched_jobs(
        config.matcher.max_jobs_per_run,
        profile_hash,
        config.matcher.max_match_attempts,
    )

    for job_id, job in candidates:
        # 1) User-defined exclusions (companies / title keywords) - no LLM cost.
        exclusion = exclude_filter.check(job)
        if not exclusion.allowed:
            repo.save_match(
                job_id,
                MatchResult(match=False, score=0, reason=f"excluded: {exclusion.reason}"),
                profile_hash,
            )
            counts.filtered_out += 1
            continue

        # 2) Deterministic rule filter (seniority, disallowed locations, ...).
        decision = rule_filter.check(job)
        if not decision.allowed:
            repo.save_match(
                job_id,
                MatchResult(match=False, score=0, reason=f"filtered: {decision.reason}"),
                profile_hash,
            )
            counts.filtered_out += 1
            continue

        # 3) DeepSeek scoring. A FatalLLMError (auth/quota/bad request) means the
        #    whole matching step is pointless, so abort it for this run.
        try:
            result = matcher.evaluate(job)
        except FatalLLMError as exc:
            log.error("Aborting matching step for the whole run: %s", exc)
            counts.llm_errors += 1
            break

        # None means a normal, retryable failure: count the attempt so a job that
        # keeps failing is eventually given up on (max_match_attempts).
        if result is None:
            if config.matcher.enabled:
                repo.increment_match_attempts(job_id)
            counts.llm_errors += 1
            continue

        repo.save_match(job_id, result, profile_hash)
        counts.sent_to_llm += 1
        if result.match:
            counts.accepted += 1
        else:
            counts.rejected += 1


def _send_digest(
    config: AppConfig,
    repo: JobRepository,
    sender: EmailSender,
    counts: RunCounts,
) -> None:
    """Email one digest of the best new matches, and mark them as 'sent'.

    The orchestrator (not `build_digest`) is responsible for slicing to
    `max_jobs_in_digest`, so exactly the jobs we record as 'sent' are the ones
    that were included. Zero candidates => no email at all.
    """
    candidates = repo.get_email_candidates(
        config.matcher.min_score, config.email.max_jobs_in_digest
    )
    candidates = candidates[: config.email.max_jobs_in_digest]
    if not candidates:
        log.info("No new matching jobs to email.")
        return

    subject, html_body, text_body = build_digest(candidates, config.email)
    message_id = sender.send(subject, html_body, text_body)
    for job in candidates:
        repo.record_email(int(job["id"]), "sent", message_id)
    counts.emailed = len(candidates)


def run(config: AppConfig, secrets: Secrets, repo: JobRepository) -> RunResult:
    """Execute one full run and return its result (status + exit code)."""
    counts = RunCounts()
    rule_filter = RuleFilter(config.filters)
    exclude_filter = ExcludeFilter(
        config.search.exclude_companies, config.search.exclude_title_keywords
    )

    # 1) Authentication is always manual; if the session is not valid we stop
    #    early with a distinct exit code so cron can retry later.
    state = ensure_authenticated(config, secrets)
    if state is not SessionState.AUTHENTICATED:
        log.error("LinkedIn authentication required (state=%s).", state.value)
        return RunResult(RunStatus.AUTH_REQUIRED, counts, EXIT_AUTH_REQUIRED)

    # 2) Build the collaborators. profile_hash ties a match to the profile+model
    #    that produced it, enabling re-scoring when either changes.
    client = DeepSeekClient(
        secrets.deepseek_api_key,
        secrets.deepseek_base_url,
        secrets.deepseek_model,
        config.matcher,
    )
    matcher = JobMatcher(client, config.profile, config.matcher)
    sender = EmailSender(secrets)
    profile_hash = compute_profile_hash(config.profile, secrets.deepseek_model)

    # 3) Scrape + match. A login wall mid-scrape aborts the run cleanly and
    #    notifies the user; `close()` always releases the browser/agent.
    scraper = build_scraper(config, secrets)
    try:
        _collect_new_jobs(scraper, config, repo, counts)
        _match_jobs(
            config, repo, matcher, rule_filter, exclude_filter, counts, profile_hash
        )
    except LoginWallError as exc:
        log.error("LinkedIn login wall detected; aborting run: %s", exc)
        try:
            sender.send_notification(
                f"{config.email.subject_prefix} LinkedIn login required",
                "The MCP scraper hit a login wall, checkpoint, or captcha and stopped. "
                "Please log in manually via scripts/login.py, then the next run can continue.",
            )
        except Exception as notify_exc:  # noqa: BLE001 - notification is best-effort
            log.error("Could not send login-required email: %s", notify_exc)
        return RunResult(RunStatus.AUTH_REQUIRED, counts, EXIT_AUTH_REQUIRED)
    finally:
        scraper.close()

    # 4) Email the digest (never called if scraping aborted above).
    _send_digest(config, repo, sender, counts)

    # Any per-job LLM error downgrades the run to PARTIAL; otherwise it's OK.
    status = RunStatus.PARTIAL if counts.llm_errors else RunStatus.OK
    exit_code = EXIT_PARTIAL if counts.llm_errors else EXIT_OK
    return RunResult(status, counts, exit_code)
