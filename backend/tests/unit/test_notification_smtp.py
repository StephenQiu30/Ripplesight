import smtplib
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from core.config import Settings
from notifications.smtp import SmtpDeliveryError, SmtpSender


class FakeSmtp:
    def __init__(self, mode="ok"):
        self.mode = mode
        self.commands = []

    def ehlo(self):
        self.commands.append("ehlo")

    def starttls(self, *, context):
        self.commands.append("tls")

    def login(self, username, password):
        self.commands.append("login")

    def send_message(self, message, *, from_addr, to_addrs):
        self.commands.append("data")
        self.message = message
        if self.mode == "unknown":
            raise smtplib.SMTPServerDisconnected("controlled loss after DATA")
        if self.mode == "partial":
            return {to_addrs[-1]: (550, b"rejected")}
        return {}

    def quit(self):
        self.commands.append("quit")

    def close(self):
        self.commands.append("close")


def test_smtp_uses_tls_and_preserves_actual_server_acceptance():
    smtp = FakeSmtp()
    settings = Settings(
        environment="test",
        database_url="postgresql+psycopg://test:test@127.0.0.1:5432/test",
        notification_smtp_enabled=True,
        notification_smtp_host="smtp.example.com",
        notification_smtp_from_email="reports@example.com",
    )
    result = SmtpSender(settings, factory=lambda *args, **kwargs: smtp).send(
        delivery_id=uuid4(),
        recipients=("reader@example.com",),
        title="日报",
        text="真实固定刊物",
        reading_url="https://hotkey.example/editions/a",
        now=datetime.now(UTC),
    )
    assert result["status"] == "smtp_accepted" and smtp.commands == [
        "ehlo",
        "tls",
        "ehlo",
        "data",
        "quit",
    ]
    assert smtp.message["Message-ID"] == result["message_id"]


@pytest.mark.parametrize("mode", ["unknown", "partial"])
def test_smtp_data_loss_or_partial_recipient_acceptance_is_unknown(mode):
    settings = Settings(
        environment="test",
        database_url="postgresql+psycopg://test:test@127.0.0.1:5432/test",
        notification_smtp_enabled=True,
        notification_smtp_host="smtp.example.com",
        notification_smtp_from_email="reports@example.com",
    )
    with pytest.raises(SmtpDeliveryError) as error:
        SmtpSender(settings, factory=lambda *args, **kwargs: FakeSmtp(mode)).send(
            delivery_id=uuid4(),
            recipients=("a@example.com", "b@example.com"),
            title="日报",
            text="内容",
            reading_url="https://hotkey.example",
            now=datetime.now(UTC),
        )
    assert error.value.uncertain
