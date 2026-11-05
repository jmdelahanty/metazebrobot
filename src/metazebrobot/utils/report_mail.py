"""Mail settings and sending for screening reports (docs/screening_report_design.md).

Settings come from the environment, or from a KEY=VALUE file at
``METAZEBROBOT_MAIL_CONFIG`` (default ``~/.config/metazebrobot/mail.env``),
so no mail server details live in the repository:

- ``METAZEBROBOT_MAIL_MODE``: ``disabled`` (default), ``outbox`` (save the
  .eml only) or ``smtp`` (save and send)
- ``METAZEBROBOT_SMTP_HOST``, ``METAZEBROBOT_SMTP_PORT`` (default 25)
- ``METAZEBROBOT_SMTP_STARTTLS`` / ``METAZEBROBOT_SMTP_SSL`` (default off)
- ``METAZEBROBOT_SMTP_USERNAME`` / ``METAZEBROBOT_SMTP_PASSWORD`` (optional)
- ``METAZEBROBOT_MAIL_FROM``: a real mailbox, e.g. ``Name <user@example.org>``
"""

from __future__ import annotations

import os
import shlex
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid, parseaddr
from pathlib import Path
from typing import Dict, List, Optional

MODES = ("disabled", "outbox", "smtp")
DEFAULT_CONFIG_PATH = "~/.config/metazebrobot/mail.env"


def _read_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        parts = shlex.split(value, comments=True)
        values[key.strip().removeprefix("export ").strip()] = parts[0] if parts else ""
    return values


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class MailConfig:
    mode: str = "disabled"
    host: Optional[str] = None
    port: int = 25
    starttls: bool = False
    ssl: bool = False
    username: Optional[str] = None
    password: Optional[str] = None
    sender: Optional[str] = None

    @classmethod
    def load(cls, environ: Optional[Dict[str, str]] = None) -> "MailConfig":
        env = dict(os.environ if environ is None else environ)
        path = Path(env.get("METAZEBROBOT_MAIL_CONFIG") or DEFAULT_CONFIG_PATH).expanduser()
        values = {**_read_env_file(path), **{k: v for k, v in env.items() if k.startswith("METAZEBROBOT_")}}
        mode = (values.get("METAZEBROBOT_MAIL_MODE") or "disabled").strip().lower()
        try:
            port = int(values.get("METAZEBROBOT_SMTP_PORT") or 25)
        except ValueError:
            port = 25
        return cls(
            mode=mode if mode in MODES else "disabled",
            host=values.get("METAZEBROBOT_SMTP_HOST") or None,
            port=port,
            starttls=_truthy(values.get("METAZEBROBOT_SMTP_STARTTLS")),
            ssl=_truthy(values.get("METAZEBROBOT_SMTP_SSL")),
            username=values.get("METAZEBROBOT_SMTP_USERNAME") or None,
            password=values.get("METAZEBROBOT_SMTP_PASSWORD") or None,
            sender=values.get("METAZEBROBOT_MAIL_FROM") or None,
        )

    def problem(self) -> Optional[str]:
        """Why sending can't happen in this mode, or None."""
        if self.mode != "smtp":
            return None
        if not self.host:
            return "METAZEBROBOT_SMTP_HOST is not set"
        if not self.sender:
            return "METAZEBROBOT_MAIL_FROM is not set"
        return None


def build_message(*, sender: Optional[str], recipients: List[str], subject: str, text: str,
                  html: str, attachment_name: str, attachment: bytes) -> EmailMessage:
    """A summary in the body (text and HTML) with the full report attached."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender or "MetaZebrobot <metazebrobot@localhost>"
    message["To"] = ", ".join(recipients)
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="metazebrobot")
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    message.add_attachment(attachment, maintype="text", subtype="html", filename=attachment_name)
    return message


def send(message: EmailMessage, config: MailConfig) -> str:
    """Send over SMTP as configured; returns the server's reply (with its queue id).

    "Accepted" only means the server queued the message; the reply's id is
    what to quote when a message never arrives. Raises on refusal.
    """
    smtp_class = smtplib.SMTP_SSL if config.ssl else smtplib.SMTP
    sender = parseaddr(message["From"])[1]
    recipients = [address for _, address in getaddresses(message.get_all("To", []))]
    with smtp_class(config.host, config.port, timeout=30) as smtp:
        smtp.ehlo()
        if config.starttls and not config.ssl:
            smtp.starttls()
            smtp.ehlo()
        if config.username:
            smtp.login(config.username, config.password or "")
        code, reply = smtp.mail(sender)
        if code != 250:
            raise smtplib.SMTPSenderRefused(code, reply, sender)
        for address in recipients:
            code, reply = smtp.rcpt(address)
            if code not in (250, 251):
                raise smtplib.SMTPRecipientsRefused({address: (code, reply)})
        code, reply = smtp.data(message.as_bytes())
        if code != 250:
            raise smtplib.SMTPDataError(code, reply)
        return reply.decode(errors="replace")
