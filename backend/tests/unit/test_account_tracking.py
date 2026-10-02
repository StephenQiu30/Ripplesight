from __future__ import annotations

import pytest
from pydantic import ValidationError

from monitors.schemas import FollowedAccountIdentityInput


@pytest.mark.parametrize(
    ("source_key", "external_id"),
    [("X", "1001"), ("x", "id with spaces"), ("x/unsafe", "1001")],
)
def test_identity_input_rejects_unstable_or_invalid_keys(
    source_key: str,
    external_id: str,
) -> None:
    with pytest.raises(ValidationError):
        FollowedAccountIdentityInput(
            source_key=source_key,
            external_id=external_id,
            alias_value="small",
            display_name="Name",
        )
