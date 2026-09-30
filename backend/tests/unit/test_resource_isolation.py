from uuid import UUID

import pytest

from core.errors import ApplicationError
from db.demo import require_demo_partition_match

_OWNER_ID = UUID("b5ab52fc-feb5-409a-a2c4-92b208db9c2e")
_FOREIGN_ID = UUID("34042a97-da60-49c9-8707-3e3eb440ff63")


def test_matching_partition_can_access_resource() -> None:
    assert require_demo_partition_match(_OWNER_ID, _OWNER_ID) is None


def test_foreign_partition_receives_the_non_disclosing_not_found_error() -> None:
    with pytest.raises(ApplicationError, match="resource_not_found") as raised:
        require_demo_partition_match(_FOREIGN_ID, _OWNER_ID)

    assert raised.value.code == "resource_not_found"
