-- jobs holds only what card-level scraping produces. Descriptions/URLs are not
-- available from the accessibility snapshot, so there are no detail columns.
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  company TEXT NOT NULL,
  location TEXT,
  url TEXT NOT NULL,
  posted_text TEXT,
  discovered_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  match_attempts INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS matches (
  job_id INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
  matched INTEGER NOT NULL,
  score INTEGER,
  reason TEXT,
  matching_skills TEXT,
  missing_skills TEXT,
  model TEXT,
  profile_hash TEXT,
  matched_at TEXT
);

CREATE TABLE IF NOT EXISTS email_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  email_status TEXT NOT NULL,
  emailed_at TEXT,
  message_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_email_job ON email_log(job_id);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  counts_json TEXT,
  error TEXT
);
