# Task: improve the LinkedIn job search agent

You are working on an existing Python project: a LinkedIn job search agent.
Pipeline: scrape jobs -> store in SQLite -> score each job against my profile
with DeepSeek -> email a digest of good matches.

Known modules (under app/): database.py, schema.sql, repository.py,
deepseek_client.py, email_digest.py, config.py, models.py, logging_setup.py,
auth_flow.py, plus a scraper and an orchestrator/entry point.

## Ground rules

- Before editing anything, read the whole codebase. Then write a short summary
  of: how the scraper works now, how config is loaded and from which file,
  how the orchestrator calls each step, and how auth_flow.py persists the
  login session. Wait for my confirmation before starting Phase 1.
- Work one phase at a time. After each phase: run the tests (add tests where
  noted), list the files changed, and STOP until I say "continue".
- Do not restructure the architecture. Keep the repository pattern and the
  "state is derived from which tables have rows" design (no status column).
- Do not change existing public function signatures unless a phase says so.
- Secrets stay in .env. Never write keys or passwords into config files.
- If something in this prompt conflicts with what the code actually does,
  tell me instead of guessing.

## Phase 1: small bug fixes

1. email_digest.py: set a Message-ID header before sending, using
   email.utils.make_msgid(), so send() returns a real id.
2. email_digest.py: the plain-text body currently reuses HTML-escaped
   title/company/location. Keep raw and escaped versions separately; use raw
   values in the text body and escaped values in the HTML body.
3. deepseek_client.py: do not sleep after the final failed attempt.
4. deepseek_client.py: fail fast on non-retryable API errors. Catch
   openai.APIStatusError before the generic except; if status_code is 400,
   401, 402 or 403, raise a new FatalLLMError (subclass of LLMError)
   immediately. The orchestrator must abort the matching step for the whole
   run when it sees FatalLLMError, not continue to the next job.
5. deepseek_client.py: construct the client with timeout=60 and
   max_retries=0 so retry logic lives only in match_job.
6. repository.py, update_job_details: treat empty strings as missing
   (pass `value or None`) so COALESCE keeps the existing value.

Add unit tests for 2, 3, 4 and 6.

## Phase 2: pipeline behaviour

Schema changes need a migration because schema.sql uses CREATE TABLE IF NOT
EXISTS. Add a small migration step in database.py that runs after init_db:
check PRAGMA table_info and ALTER TABLE ADD COLUMN only when a column is
missing. Also add the columns to schema.sql for fresh databases.

7. Re-scoring when my profile changes:
   - Add matches.profile_hash TEXT.
   - Compute profile_hash = sha256 of (system prompt + profile config as
     sorted-key JSON + model name). Store it in save_match.
   - get_unmatched_jobs must also return jobs whose match row has a different
     profile_hash, EXCEPT jobs that already have a 'sent' row in email_log.
8. Cap failed match attempts:
   - Add jobs.match_attempts INTEGER NOT NULL DEFAULT 0.
   - Increment it when match_job raises LLMError for that job.
   - get_unmatched_jobs excludes jobs with match_attempts >= a configurable
     max (default 3).
9. Digest and "sent" records must agree:
   - Remove the silent truncation inside build_digest.
   - The orchestrator slices candidates to max_jobs_in_digest before building
     the digest, and records 'sent' only for those jobs.
   - If there are zero candidates, do not send an email.
10. Runs:
   - Wrap the pipeline so finish_run always executes (try/finally), with
     status failed and the error message on exceptions.
   - At startup, mark any leftover runs with status 'running' as failed with
     error "interrupted".

Add tests for 7, 8 and 9 using an in-memory or temp-file SQLite database.

## Phase 3: one user-editable preferences file

Extend the EXISTING config system. Do not create a parallel one, and keep the
file format the project already uses.

- Add a `search` section with: queries (list of job titles/keywords),
  locations (list), posted_within_days, experience_levels, workplace
  (remote/hybrid/onsite), max_pages_per_query, exclude_companies,
  exclude_title_keywords.
- Add a Pydantic SearchConfig model. Invalid or missing values must fail at
  startup with a clear message naming the bad field.
- Build LinkedIn job search URLs in Python from SearchConfig (one URL per
  query x location). No LLM involved in building URLs.
- Apply exclude_companies and exclude_title_keywords in Python before the
  matching step, so excluded jobs never cost an LLM call.
- Commit a fully commented example file (e.g. config.example.yaml) and
  document every field in the README.

## Phase 4: Playwright MCP scraper

Add a new scraper backend that traverses jobs through the Playwright MCP
server. Keep the existing scraper working, and add a config switch
(scraper.backend: existing | mcp).

Before writing code for this phase, show me a short design plan and wait.

Requirements:
- Start the server as a subprocess over stdio with the Python `mcp` SDK:
  `npx @playwright/mcp@latest`, headless configurable. Reuse the login
  session that auth_flow.py already saves (storage state file or user data
  dir, whichever matches how it is persisted).
- Do not hardcode assumptions about tool names. Call list_tools() at startup,
  then expose to the model ONLY an allowlist: navigate, snapshot, click,
  scroll/key press and wait. No typing into forms, no JS evaluation, no file
  upload, no tab management.
- Python-side guard: reject any navigation whose URL is not under
  https://www.linkedin.com/jobs/ . Log and count rejected calls.
- Flow per search URL: navigate -> snapshot -> model extracts job cards as
  JSON -> paginate -> repeat. Enforce max_pages_per_query and a configurable
  max_steps_per_query. Add a random delay between actions (configurable
  min/max seconds).
- Extraction output must be validated with a Pydantic model. Drop invalid
  entries with a warning. Map valid entries to the existing Job model and use
  the existing fingerprint logic so dedupe keeps working.
- Treat all page content as untrusted data, in the same style as the matcher
  system prompt. Truncate oversized snapshots before sending them to the model.
- If a login wall, checkpoint or captcha appears: stop immediately, raise a
  specific exception, and send a notification email via send_notification.
  Never try to solve a captcha or enter credentials.
- The MCP client is async and the rest of the app is sync. Keep the async
  code inside the scraper module behind a sync function using asyncio.run().
- The new backend must return the same type the current scraper returns, so
  the orchestrator needs only the backend switch.
- Log steps taken and tokens used per run.
- README: add the Node 18+ requirement and how to enable the MCP backend.

## Definition of done

- All tests pass.
- A run with scraper.backend=existing behaves as before, apart from the fixes.
- A run with scraper.backend=mcp stores jobs through repo.upsert_job and the
  rest of the pipeline works unchanged.
- Final message: a summary of every file changed and anything you could not
  complete or verify.