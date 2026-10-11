"""Cron entry point: ``python -m app``.

Responsibilities of this thin wrapper:
1. Load config + set up logging.
2. Acquire the single-run file lock (so cron jobs never overlap).
3. Open the DB, run schema migrations, and close out any run left 'running'
   by a previous crash.
4. Call ``runner.run()`` and *always* record a final row in the `runs` table,
   even if it raises.
5. Return a documented exit code to cron.
"""

from __future__ import annotations

import time

from app.config import load_config, load_secrets
from app.db.database import connect, init_db
from app.db.repository import JobRepository
from app.logging_setup import get_logger, setup_logging
from app.models import RunStatus
from app.runner import EXIT_FATAL, EXIT_LOCKED, run
from app.utils.locks import FileLock


def main() -> int:
    config = load_config()
    setup_logging(config.log_dir, config.runtime.log_level)
    log = get_logger("main")
    log.info("LinkedIn Job Hunter starting (db=%s).", config.database_path)

    # Prevent overlapping cron executions: if another run holds the lock, exit
    # quietly (code 4) and let the next scheduled run try again.
    lock = FileLock(config.lock_path)
    if not lock.acquire():
        log.warning("Another run holds the lock (%s); skipping this execution.", config.lock_path)
        return EXIT_LOCKED

    try:
        secrets = load_secrets()
        conn = connect(config.database_path)
        init_db(conn)  # creates tables on first run, then migrates columns
        repo = JobRepository(conn)

        # A crash can leave runs stuck in 'running'; mark them failed now.
        stale = repo.fail_stale_runs()
        if stale:
            log.warning("Marked %d interrupted run(s) as failed.", stale)

        run_id = repo.start_run()
        started = time.monotonic()
        result = None
        error: str | None = None
        try:
            result = run(config, secrets, repo)
        except Exception as exc:  # top-level safety net
            error = str(exc)
            log.exception("Fatal error during run")
        finally:
            # Always finalize the run row: SUCCESS carries the counts, otherwise
            # we record ERROR plus the exception message.
            if result is not None:
                repo.finish_run(run_id, result.status, result.counts)
            else:
                repo.finish_run(run_id, RunStatus.ERROR, error=error or "unknown error")
            duration = time.monotonic() - started
            status = result.status.value if result is not None else RunStatus.ERROR.value
            counts = result.counts.model_dump() if result is not None else None
            log.info(
                "Run finished status=%s duration=%.1fs counts=%s",
                status,
                duration,
                counts,
            )

        # Close the DB before returning, whichever branch we took above.
        try:
            if result is not None:
                return result.exit_code
            return EXIT_FATAL
        finally:
            conn.close()
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
