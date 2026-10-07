from __future__ import annotations

import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from queue import Empty, Queue
from threading import Event, Thread
from time import monotonic
from typing import Literal

from core.errors import ApplicationError

_DELIVERY_DEADLINE_SECONDS = 10


class SmtpEmailAdapter:
    """Authentication mail with verified TLS and an overall delivery deadline."""

    def __init__(
        self,
        host: str | None,
        port: int,
        tls: Literal["starttls", "ssl"],
        username: str | None,
        password: str | None,
        from_email: str | None,
    ) -> None:
        self._host = host
        self._port = port
        self._tls = tls
        self._username = username
        self._password = password
        self._from_email = from_email

    def send_code(self, email: str, code: str) -> None:
        if (
            not self._host
            or not self._from_email
            or self._tls not in {"starttls", "ssl"}
            or bool(self._username) != bool(self._password)
            or not re.fullmatch(r"[0-9]{6}", code)
            or not re.fullmatch(r"[^\s@,;<>\x00-\x1f\x7f]+@[^\s@,;<>\x00-\x1f\x7f]+", email)
        ):
            raise ApplicationError("email_delivery_unavailable")
        try:
            message = EmailMessage()
            message["From"] = self._from_email
            message["To"] = email
            message["Subject"] = "Ripplesight登录验证码"
            message.set_content(
                f"你的登录验证码是 {code}。5 分钟内有效且只能使用一次。\n"
                "如果不是你发起的登录。请忽略这封邮件。\n"
            )
        except ValueError:
            raise ApplicationError("email_delivery_unavailable") from None

        deadline = monotonic() + _DELIVERY_DEADLINE_SECONDS
        cancelled = Event()
        result: Queue[bool] = Queue(maxsize=1)
        connection: list[smtplib.SMTP] = []

        def remaining(client: smtplib.SMTP | None = None) -> float:
            seconds = deadline - monotonic()
            if cancelled.is_set() or seconds <= 0:
                raise TimeoutError("authentication email deadline exceeded")
            if client is not None and client.sock is not None:
                client.sock.settimeout(seconds)
            return seconds

        def deliver() -> None:
            client: smtplib.SMTP | None = None
            success = False
            try:
                # A fixed local_hostname avoids an unnecessary local reverse-DNS lookup.
                context = ssl.create_default_context()
                client = (
                    smtplib.SMTP_SSL(
                        host=self._host or "",
                        port=self._port,
                        local_hostname="localhost",
                        timeout=remaining(),
                        context=context,
                    )
                    if self._tls == "ssl"
                    else smtplib.SMTP(
                        host=self._host or "",
                        port=self._port,
                        local_hostname="localhost",
                        timeout=remaining(),
                    )
                )
                connection.append(client)
                remaining(client)
                client.ehlo()
                if self._tls == "starttls":
                    remaining(client)
                    client.starttls(context=context)
                    remaining(client)
                    client.ehlo()
                if self._username and self._password:
                    remaining(client)
                    client.login(self._username, self._password)
                remaining(client)
                rejected = client.send_message(message)
                remaining(client)
                success = not rejected
            except (OSError, ValueError, smtplib.SMTPException):
                success = False
            finally:
                if client is not None:
                    client.close()
                result.put(success)

        # DNS resolution is not governed by a socket timeout. A daemon worker plus
        # cancellation bounds the caller too; a late DNS result cannot send the message.
        Thread(target=deliver, name="identity-smtp-delivery", daemon=True).start()
        try:
            delivered = result.get(timeout=max(0, deadline - monotonic()))
        except Empty:
            cancelled.set()
            active_socket = connection[0].sock if connection else None
            if active_socket is not None:
                try:
                    active_socket.shutdown(socket.SHUT_RDWR)
                    active_socket.close()
                except OSError:
                    pass
            raise ApplicationError("email_delivery_unavailable") from None
        if not delivered:
            raise ApplicationError("email_delivery_unavailable")
