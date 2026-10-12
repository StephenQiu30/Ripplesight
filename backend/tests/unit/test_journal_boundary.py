"""Reject unsafe authority identities before a connection pool is created."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from evidence import journal


@pytest.mark.parametrize("defect", ["same_database", "driver", "role", "epoch", "remote_test"])
def test_unsafe_journal_settings_never_create_engine(monkeypatch, defect):
    factory = MagicMock()
    monkeypatch.setattr(journal, "create_engine", factory)
    target = "postgresql+psycopg://reader@127.0.0.1/hotkey_test_journal"
    source = "postgresql+psycopg://source@127.0.0.1/hotkey_test_business"
    epoch = 1
    if defect == "same_database":
        target = source
    elif defect == "driver":
        target = "sqlite:///local.db"
    elif defect == "role":
        target = "postgresql+psycopg://127.0.0.1/hotkey_test_journal"
    elif defect == "epoch":
        epoch = True
    else:
        target = "postgresql+psycopg://reader@remote.example/hotkey_test_journal"
    with pytest.raises(journal.JournalUnavailableError):
        journal.RestrictionJournal(
            database_url=target, source_database_url=source, ledger_id=uuid4(), epoch=epoch
        )
    factory.assert_not_called()
