"""Email digest formatting and SMTP delivery."""

from __future__ import annotations

import html as html_lib
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from app.config import EmailConfig, Secrets
from app.logging_setup import get_logger

log = get_logger(__name__)


def build_digest(
    jobs: list[dict],
    email_config: EmailConfig,
) -> tuple[str, str, str]:
    """Return (subject, html_body, text_body) for the digest.

    Callers are responsible for slicing to the desired digest size; this
    function renders exactly the jobs it is given.
    """
    count = len(jobs)
    subject = f"{email_config.subject_prefix} {count} New Matching LinkedIn Jobs"

    text_parts = [subject, "=" * len(subject), ""]
    html_parts = [
        "<html><body style=\"font-family:Arial,sans-serif;line-height:1.5\">",
        f"<h2>{html_lib.escape(subject)}</h2>",
    ]

    for job in jobs:
        # Keep raw (for the plain-text body) and HTML-escaped (for the HTML body)
        # versions separate, so neither body shows encoded entities to the reader.
        raw_title = str(job.get("title") or "Unknown")
        raw_company = str(job.get("company") or "Unknown")
        raw_location = str(job.get("location") or "N/A")
        raw_reason = str(job.get("reason") or "")
        raw_url = str(job.get("url") or "")
        raw_missing = ", ".join(job.get("missing_skills") or []) or "None"
        raw_matching = ", ".join(job.get("matching_skills") or []) or "None"
        score = job.get("score")

        title = html_lib.escape(raw_title)
        company = html_lib.escape(raw_company)
        location = html_lib.escape(raw_location)
        reason = html_lib.escape(raw_reason)
        url = html_lib.escape(raw_url)
        missing = html_lib.escape(raw_missing)
        matching = html_lib.escape(raw_matching)

        text_parts += [
            f"{raw_title} - {raw_company}",
            f"Location: {raw_location}",
            f"Match: {score}%",
            f"Why: {raw_reason}",
            f"Matching: {raw_matching}",
            f"Missing: {raw_missing}",
            f"Apply: {raw_url}",
            "-" * 40,
            "",
        ]

        html_parts += [
            "<div style=\"border:1px solid #ddd;border-radius:8px;padding:12px;margin:12px 0\">",
            f"<h3 style=\"margin:0\">{title} &mdash; {company}</h3>",
            f"<p style=\"margin:4px 0\"><b>Location:</b> {location} &nbsp; "
            f"<b>Match:</b> {html_lib.escape(str(score))}%</p>",
            f"<p style=\"margin:4px 0\"><b>Why:</b> {reason}</p>",
            f"<p style=\"margin:4px 0\"><b>Matching:</b> {matching}</p>",
            f"<p style=\"margin:4px 0\"><b>Missing:</b> {missing}</p>",
            f"<p style=\"margin:4px 0\"><a href=\"{url}\">Apply on LinkedIn</a></p>",
            "</div>",
        ]

    html_parts.append("</body></html>")
    return subject, "\n".join(html_parts), "\n".join(text_parts)


class EmailSender:
    """Sends the digest (and plain notifications) over SMTP with STARTTLS.

    Only needs secrets; the digest's formatting options are handled by
    :func:`build_digest` from the caller's `EmailConfig`.
    """

    def __init__(self, secrets: Secrets) -> None:
        self.secrets = secrets

    def _recipients(self) -> list[str]:
        # EMAIL_TO may be a comma-separated list; fall back to the SMTP user.
        raw = self.secrets.email_to or self.secrets.smtp_user
        return [addr.strip() for addr in raw.split(",") if addr.strip()]

    def send(self, subject: str, html_body: str, text_body: str) -> str:
        """Send a multipart (text + HTML) email and return its Message-ID."""
        sender = self.secrets.email_from or self.secrets.smtp_user
        recipients = self._recipients()
        if not sender or not recipients or not self.secrets.smtp_password:
            raise RuntimeError("Email settings are incomplete (from/to/password)")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        # Set a real Message-ID up front so send() can return it for email_log.
        message["Message-ID"] = make_msgid()
        message.set_content(text_body)  # plain text: the safe fallback
        message.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(self.secrets.smtp_host, self.secrets.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(self.secrets.smtp_user or sender, self.secrets.smtp_password)
            server.send_message(message)

        message_id = message.get("Message-ID") or ""
        log.info("Email sent to %s", ", ".join(recipients))
        return message_id

    def send_notification(self, subject: str, body: str) -> str:
        """Send a short plain-text notification (e.g. 'login required')."""
        return self.send(subject, f"<p>{html_lib.escape(body)}</p>", body)
