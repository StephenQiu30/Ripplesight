from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy import Engine

from core.errors import ApplicationError
from db.owners import require_owner_id

_OWNER_ID = UUID("b5ab52fc-feb5-409a-a2c4-92b208db9c2e")


def test_matching_account_can_be_used_as_an_explicit_maintenance_target() -> None:
    session = MagicMock()
    session.get_bind.return_value = MagicMock(spec=Engine)
    connection = session.get_bind.return_value.connect.return_value.__enter__.return_value
    connection.scalar.return_value = _OWNER_ID
    assert require_owner_id(session, _OWNER_ID) == _OWNER_ID


def test_unknown_account_receives_the_non_disclosing_not_found_error() -> None:
    session = MagicMock()
    session.get_bind.return_value = MagicMock(spec=Engine)
    connection = session.get_bind.return_value.connect.return_value.__enter__.return_value
    connection.scalar.return_value = None
    with pytest.raises(ApplicationError, match="resource_not_found") as raised:
        require_owner_id(session, _OWNER_ID)
    assert raised.value.code == "resource_not_found"
