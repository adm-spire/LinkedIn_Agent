# AGENTS.md — LinkedIn Job Hunter Agent

## 1. Project Goal

Build a local, autonomous **LinkedIn Job Hunter Agent** that periodically searches LinkedIn for new job openings matching the user's target roles and sends a concise email digest containing relevant opportunities.

The project should be designed to run automatically through a Linux cron job.

The primary target roles are:

* AI Engineer
* AI/ML Engineer
* Software Engineer
* Software Developer
* SDE
* Backend Engineer
* Python Engineer
* AI Automation Engineer
* Agentic AI Engineer

The project should be extensible so additional roles, locations, experience ranges, and search queries can be configured later.

The user has access to a DeepSeek LLM API and wants DeepSeek to perform semantic job matching and reasoning.

---

# 2. IMPORTANT: Planning Before Implementation

When this repository is initially empty or the project has not yet been designed:

**DO NOT immediately start implementing the project.**

First inspect the repository and understand the environment.

Then produce a detailed architecture/design proposal in **plan mode**.

The plan must cover:

* project architecture
* components
* data flow
* Playwright architecture
* persistent browser profile
* LinkedIn session management
* job extraction
* job normalization
* SQLite schema
* duplicate detection
* DeepSeek integration
* structured LLM output
* email notifications
* cron execution
* error handling
* logging
* configuration
* testing strategy
* security considerations
* recovery behavior
* implementation phases
* dependencies

After discussing/refining the architecture, write the final agreed implementation plan to:

```text
final_plan.md
```

`final_plan.md` is the implementation contract.

Once `final_plan.md` exists, use it as the primary source of truth for implementation.

Do not silently redesign the architecture while implementing unless a technical problem makes the plan impossible. If a major architectural change becomes necessary, update `final_plan.md` first.

---

# 3. Core Architecture

The intended architecture is:

```text
Linux cron
     |
     v
Job Hunter Application
     |
     v
Persistent Playwright Browser
     |
     v
LinkedIn
     |
     v
Job Search / Extraction
     |
     v
Job Normalization
     |
     v
SQLite
     |
     v
New-job detection
     |
     v
Rule-based filtering
     |
     v
DeepSeek Job Matching Agent
     |
     v
Relevant jobs
     |
     v
Email Digest
```

The system is intentionally focused on **LinkedIn only**.

Do NOT add:

* Indeed
* Glassdoor
* Wellfound
* Greenhouse
* Lever
* generic web search
* other job boards

unless explicitly requested later.

---

# 4. LinkedIn Is the Only Job Source

LinkedIn is the sole external job source for this project.

The system should search LinkedIn using Playwright.

Do not introduce a paid job-search API.

Do not build an external scraping API dependency.

The DeepSeek API is allowed and expected for semantic job matching.

---

# 5. Browser Architecture

Use Playwright with a **dedicated persistent browser profile**.

Do not use the user's normal Chrome profile.

Create a project-specific browser profile such as:

```text
data/browser_profile/
```

or another location defined by the final architecture.

The persistent profile should retain browser state between executions where LinkedIn permits it.

The intended lifecycle is:

```text
First execution
    |
    v
Launch persistent Playwright profile
    |
    v
User manually logs into LinkedIn
    |
    v
Session persists
    |
    v
Future cron executions reuse profile
```

The agent must not require the user to manually log in on every execution.

---

# 6. LinkedIn Authentication / Session Expiration

Authentication must remain under the user's control.

The system should **not attempt to bypass LinkedIn authentication, CAPTCHA, MFA, security challenges, or other access controls.**

Do not implement:

* CAPTCHA solving
* CAPTCHA bypass
* MFA bypass
* credential theft
* extraction of passwords
* browser security bypasses
* anti-bot evasion mechanisms
* stealth plugins specifically intended to defeat detection
* fingerprint spoofing intended to evade LinkedIn protections

The user will manually authenticate when required.

## Required behavior

If the persistent session is valid:

```text
launch browser
    |
    v
detect authenticated LinkedIn session
    |
    v
continue automatically
```

If the session has expired:

```text
launch browser
    |
    v
detect login-required state
    |
    v
notify user that manual LinkedIn login is required
    |
    v
allow user to authenticate manually
    |
    v
detect successful authentication
    |
    v
continue job search
```

LinkedIn must NOT simply be skipped permanently.

Because LinkedIn is the only source, failure to authenticate should be treated as an operational failure requiring user attention.

The implementation should define a sensible timeout for waiting for manual authentication.

If the timeout expires:

* log the failure
* send a clear email notification if possible
* exit cleanly
* allow the next cron execution to retry

Do not repeatedly hammer LinkedIn.

---

# 7. Login Detection

The implementation must have a dedicated session/authentication module.

For example:

```text
browser/
    profile.py
    session.py
```

The exact implementation should be determined during planning.

Avoid relying on one fragile CSS selector when possible.

Use multiple reasonable signals to determine whether the browser is:

1. authenticated
2. unauthenticated
3. showing a login/security challenge
4. in an unexpected state

The system should fail safely when the state cannot be determined.

---

# 8. Job Searching

The agent should support configurable LinkedIn search queries.

Example searches:

```text
AI Engineer
Machine Learning Engineer
Software Engineer
Software Developer
SDE
Backend Engineer
Python Engineer
AI Automation Engineer
Agentic AI Engineer
```

Search configuration should not be hard-coded throughout the application.

Put configurable values in a configuration file or environment/config system.

The architecture should support:

* multiple search queries
* location filters
* experience filters where LinkedIn exposes them
* remote/hybrid/on-site preferences where applicable
* pagination or controlled scrolling

Do not create an uncontrolled infinite crawler.

The number of pages/results searched per query should be configurable.

---

# 9. Responsible Browser Automation

Use Playwright to interact with LinkedIn pages as a normal browser automation workflow.

The implementation should:

* use reasonable request/navigation frequency
* avoid unnecessary page reloads
* avoid aggressive crawling
* avoid infinite scrolling
* use configurable limits
* stop when sufficient results have been collected
* handle navigation failures gracefully

Do not implement techniques whose purpose is to circumvent LinkedIn's bot detection or access controls.

The goal is a reliable personal automation tool, not an anti-bot evasion system.

---

# 10. Job Data Model

Normalize every extracted LinkedIn job into a consistent internal representation.

At minimum:

```text
job_id / stable identifier if available
title
company
location
url
description
posted_text
source
discovered_at
```

If additional useful fields are available reliably, the architecture may include:

```text
employment_type
experience_level
salary
remote_status
company_url
```

Do not make fields mandatory if LinkedIn does not reliably expose them.

---

# 11. SQLite

Use SQLite for persistent state.

SQLite should store:

* discovered jobs
* normalized job information
* first discovery time
* last seen time
* matching result
* DeepSeek score
* matching explanation
* missing skills
* email status

The exact schema should be finalized in `final_plan.md`.

The database must allow the application to distinguish:

```text
NEW JOB
ALREADY SEEN JOB
ALREADY EMAILED JOB
```

---

# 12. Deduplication

Duplicate detection is a core requirement.

The same job may appear in multiple LinkedIn searches.

For example:

```text
Search: AI Engineer
Search: Python Engineer
Search: Backend Engineer
```

may all return the same posting.

The system should deduplicate jobs before sending them to DeepSeek and before emailing them.

Prefer a stable LinkedIn job identifier when available.

Otherwise use a carefully designed deterministic identifier based on available job fields.

Do not rely solely on the job title.

---

# 13. Rule-Based Filtering Before DeepSeek

Do not send every scraped job to DeepSeek.

Use inexpensive deterministic filtering first.

Examples:

* target title
* location
* experience level
* obvious seniority
* required experience
* obvious role mismatch

For example:

```text
Senior Software Engineer
Staff Software Engineer
Engineering Manager
Director of Engineering
```

may be rejected based on the user's configured experience target.

The exact filtering rules should be configurable.

---

# 14. DeepSeek Integration

DeepSeek is the semantic reasoning component.

The system should send candidate jobs to DeepSeek only after basic filtering.

DeepSeek should evaluate:

* role relevance
* skill match
* experience match
* technology overlap
* AI/LLM relevance
* backend relevance
* overall suitability

The LLM should produce **structured JSON**, not free-form prose.

Example conceptual output:

```json
{
  "match": true,
  "score": 87,
  "reason": "Strong match because the role requires Python, FastAPI and LLM application development.",
  "matching_skills": [
    "Python",
    "FastAPI",
    "LLM",
    "REST APIs"
  ],
  "missing_skills": [
    "AWS"
  ]
}
```

The exact schema must be finalized during planning.

The application must validate the LLM response.

Never blindly trust arbitrary LLM output.

If the response is malformed:

* retry a limited number of times if appropriate
* log the failure
* do not crash the entire job pipeline

---

# 15. Candidate Profile

The user's profile should be represented as structured configuration rather than repeatedly embedded throughout the code.

Relevant profile information includes:

```text
Education:
BTech Computer Science

Experience:
~1 year software development experience

Current technical experience:
Python
FastAPI
React
SQL
Docker
Linux
LangGraph
LLM agents
Playwright
Selenium
REST APIs

Target:
AI Engineer
Software Engineer
Backend Engineer
Python Engineer
AI/LLM Engineer
Agentic AI
AI Automation
```

The exact candidate profile should be configurable.

Do not hard-code personal information into multiple modules.

---

# 16. Email Digest

Do not send one email per job.

Generate a digest containing the relevant new jobs found during the run.

Example:

```text
Subject:
[Job Hunter] 6 New Matching LinkedIn Jobs

AI Engineer — Company A
Location: Bangalore
Match: 92%

Why:
Strong Python + LLM + backend overlap.

Missing:
AWS

Apply:
<LinkedIn URL>
```

The email system should support:

* SMTP or another simple email mechanism
* environment-based credentials
* configurable recipient
* HTML email if useful
* plain-text fallback

Never hard-code email credentials.

---

# 17. Secrets

All secrets must come from environment variables or an appropriate local secret mechanism.

Never commit:

* DeepSeek API key
* email password
* SMTP credentials
* LinkedIn credentials
* cookies
* session tokens
* browser secrets

The repository must include an example environment file such as:

```text
.env.example
```

but it must contain only placeholders.

---

# 18. Logging

The application must have useful structured logging.

At minimum log:

```text
application start
LinkedIn browser launch
authentication state
search query
number of jobs extracted
number of duplicates
number of new jobs
number sent to DeepSeek
number accepted
number rejected
email status
errors
execution duration
```

Do not log sensitive information.

Never log:

* passwords
* session cookies
* API keys
* authentication tokens

---

# 19. Error Handling

The application should fail gracefully.

Possible failures:

```text
LinkedIn unavailable
browser launch failure
session expired
login required
navigation timeout
DOM changed
job extraction failure
SQLite failure
DeepSeek API failure
DeepSeek malformed output
email failure
```

A single bad job should not terminate the entire run.

Use appropriate exception boundaries.

The cron process should exit with a meaningful status code.

---

# 20. Cron

The final project must support execution through Linux cron.

The application should be executable with something conceptually similar to:

```bash
python -m app
```

or:

```bash
python main.py
```

The exact entry point should be defined in `final_plan.md`.

Cron should invoke the application's virtual environment explicitly.

Example conceptual schedule:

```text
Once or twice per day
```

Do not hard-code the cron schedule into application logic.

Provide documentation explaining how to configure cron.

---

# 21. Browser Lifecycle and Cron

The implementation must carefully consider the interaction between:

```text
cron
+
Playwright
+
persistent browser profile
```

Do not assume multiple concurrent processes can safely use the same browser profile.

Prevent overlapping cron executions.

Possible approaches include:

* lock file
* process lock
* OS-level locking
* another appropriate mechanism

The final approach should be documented in `final_plan.md`.

---

# 22. Testing

The project should have tests for important deterministic components.

At minimum test:

```text
job normalization
deduplication
rule-based filtering
DeepSeek response validation
database operations
authentication-state classification
email formatting
```

Do not make the test suite depend on live LinkedIn access.

Use fixtures/mock data for LinkedIn pages and LLM responses where appropriate.

Live LinkedIn testing should be separated from unit tests.

---

# 23. Playwright MCP vs Application Runtime

The project may use Playwright MCP during development if useful for exploration/debugging.

However, the final production architecture should clearly distinguish:

```text
development / agent-assisted browser exploration
```

from:

```text
scheduled production job collector
```

Do not unnecessarily make the cron application depend on an interactive MCP server if direct Playwright automation is simpler and more reliable.

If Playwright MCP is chosen as part of the final runtime architecture, explain exactly why in `final_plan.md`.

Prefer the simplest reliable architecture.

---

# 24. Agentic Design

Do not force LangGraph or an LLM agent framework into every component.

The project should use deterministic code where deterministic code is sufficient.

A reasonable division is:

```text
Python:
    browser control
    extraction
    normalization
    database
    deduplication
    scheduling
    email

DeepSeek:
    semantic job matching
    reasoning about candidate/job fit
```

An agent framework may be introduced later if it provides a concrete benefit.

Do not add LangGraph merely because the project is called an agent.

---

# 25. Security

Treat LinkedIn pages and job descriptions as untrusted external content.

Do not allow job descriptions to directly control application behavior.

In particular, the LLM must not be instructed to execute arbitrary commands contained in job descriptions.

Job descriptions are data.

Never allow scraped content to become executable instructions.

---

# 26. Maintainability

Prefer:

* small modules
* clear interfaces
* type hints
* dataclasses/Pydantic models where appropriate
* dependency injection where useful
* configuration-driven behavior
* explicit error handling
* readable code

Avoid:

* giant `main.py`
* global mutable state
* hard-coded selectors everywhere
* duplicated logic
* unnecessary frameworks
* unnecessary abstractions

---

# 27. Documentation

The final project should contain a useful README covering:

1. Project purpose
2. Architecture
3. Requirements
4. Installation
5. Environment variables
6. First-time LinkedIn login
7. Persistent browser profile
8. How session expiration is handled
9. DeepSeek configuration
10. Email configuration
11. Running manually
12. Running through cron
13. Database
14. Testing
15. Troubleshooting

Explain clearly that the first LinkedIn authentication is manual.

Also explain what happens when the LinkedIn session expires.

---

# 28. Implementation Philosophy

Build the smallest reliable version first.

Preferred progression:

```text
Phase 1
Playwright → LinkedIn → extract jobs

Phase 2
SQLite → persistence + deduplication

Phase 3
Rule-based filtering

Phase 4
DeepSeek matching

Phase 5
Email digest

Phase 6
Session expiration handling

Phase 7
Cron + locking

Phase 8
Testing + documentation
```

Do not implement every possible feature before verifying the previous phase works.

After each significant phase, run tests and verify the implementation.

---

# 29. Definition of Done

The project is considered complete when:

1. The user can manually authenticate to LinkedIn once using the dedicated Playwright profile.
2. The persistent profile is reused between executions.
3. The agent can search configured LinkedIn job queries.
4. Jobs are normalized into a consistent schema.
5. Jobs are stored in SQLite.
6. Duplicate jobs are detected.
7. Previously emailed jobs are not emailed again.
8. Basic deterministic filtering occurs before DeepSeek.
9. DeepSeek evaluates remaining jobs.
10. DeepSeek responses are validated.
11. Relevant new jobs are placed into an email digest.
12. The application can run from Linux cron.
13. Concurrent executions are prevented.
14. LinkedIn session expiration is detected.
15. When authentication expires, the user is notified and can manually log in.
16. After successful manual authentication, the agent can continue.
17. Authentication/security controls are not bypassed.
18. Secrets are not committed.
19. The project has meaningful logs.
20. The project has tests for deterministic components.
21. The README explains setup and operation.

---

# 30. Final Instruction to the Coding Agent

Before writing implementation code:

**Think through the architecture carefully.**

In plan mode:

1. Inspect the repository.
2. Identify constraints.
3. Identify technical risks.
4. Propose the architecture.
5. Explain important design decisions.
6. Identify assumptions.
7. Identify components and interfaces.
8. Define the SQLite schema.
9. Define the DeepSeek structured-output contract.
10. Define the LinkedIn session lifecycle.
11. Define cron behavior.
12. Define failure/recovery behavior.
13. Define testing strategy.
14. Produce the final implementation plan.

Write the agreed final plan to:

```text
final_plan.md
```

Only after `final_plan.md` has been finalized should implementation begin.

During implementation:

* follow `final_plan.md`
* inspect existing code before modifying it
* avoid unnecessary rewrites
* keep changes incremental
* run tests after meaningful changes
* update documentation when behavior changes
* update `final_plan.md` if a major architectural decision changes

The final result should be a **working personal LinkedIn job-monitoring system**, not merely a prototype or architectural demo.
