from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Any
from uuid import UUID

from core.config import Settings


class SmtpDeliveryError(Exception):
    def __init__(self, code: str, *, uncertain: bool = False):
        super().__init__(code)
        self.code, self.uncertain = code, uncertain


class SmtpSender:
    def __init__(self, settings: Settings, *, factory: Callable[..., Any] | None = None):
        self._settings, self._factory = settings, factory

    def send(
        self,
        *,
        delivery_id: UUID,
        recipients: tuple[str, ...],
        title: str,
        text: str,
        reading_url: str,
        now: datetime,
    ) -> dict[str, object]:
        settings = self._settings
        if (
            not settings.notification_smtp_enabled
            or settings.notification_smtp_host is None
            or settings.notification_smtp_from_email is None
            or not recipients
        ):
            raise SmtpDeliveryError("smtp_unconfigured")
        domain = settings.notification_smtp_from_email.rsplit("@", 1)[-1]
        message = EmailMessage()
        message["From"] = settings.notification_smtp_from_email
        message["To"] = ", ".join(recipients)
        message["Subject"] = title.replace("\r", " ").replace("\n", " ")
        message["Date"] = format_datetime(now)
        message["Message-ID"] = f"<{delivery_id}@{domain}>"
        message.set_content(text + "\n\n" + reading_url)
        smtp = None
        sending = False
        try:
            factory = self._factory or (
                smtplib.SMTP_SSL if settings.notification_smtp_tls == "ssl" else smtplib.SMTP
            )
            options: dict[str, Any] = {"timeout": settings.notification_smtp_timeout_seconds}
            if settings.notification_smtp_tls == "ssl":
                options["context"] = ssl.create_default_context()
            smtp = factory(
                settings.notification_smtp_host, settings.notification_smtp_port, **options
            )
            smtp.ehlo()
            if settings.notification_smtp_tls == "starttls":
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if settings.notification_smtp_username is not None:
                if settings.notification_smtp_password is None:
                    raise SmtpDeliveryError("smtp_unconfigured")
                smtp.login(
                    settings.notification_smtp_username.get_secret_value(),
                    settings.notification_smtp_password.get_secret_value(),
                )
            sending = True
            rejected = smtp.send_message(
                message, from_addr=settings.notification_smtp_from_email, to_addrs=list(recipients)
            )
            if rejected:
                raise SmtpDeliveryError("smtp_partial_acceptance", uncertain=True)
            return {
                "transport": "smtp",
                "status": "smtp_accepted",
                "message_id": str(message["Message-ID"]),
                "accepted_recipient_count": len(recipients),
            }
        except SmtpDeliveryError:
            raise
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
            raise SmtpDeliveryError("smtp_rejected") from None
        except (smtplib.SMTPException, OSError):
            raise SmtpDeliveryError(
                "smtp_result_unknown" if sending else "smtp_connect_failed", uncertain=sending
            ) from None
        finally:
            if smtp is not None:
                try:
                    smtp.quit()
                except (smtplib.SMTPException, OSError):
                    with suppress(smtplib.SMTPException, OSError):
                        smtp.close()
