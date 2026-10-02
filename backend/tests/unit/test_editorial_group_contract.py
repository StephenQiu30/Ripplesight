from uuid import uuid4

import pytest
from pydantic import ValidationError

from jobs.editorial_schemas import EditorialGroupManifest, EditorialGroupMember
from sources.editorial_schemas import EditorialMaterial


def member(handle, *, ident=None):
    ident = ident or uuid4()
    return EditorialGroupMember(
        profile_id=ident,
        source_key=f"ed_x_search_{ident.hex}",
        configuration_version=1,
        revision=2,
        policy_version=1,
        configuration_sha256="a" * 64,
        handle=handle,
        cursor_json="{}",
    )


def test_group_manifest_freezes_distinct_members_and_derived_query():
    one, two = member("one"), member("two")
    command = EditorialGroupManifest(
        owner_id=uuid4(),
        connection_id=uuid4(),
        connection_version=1,
        participation_mode="editorial",
        query="(from:one OR from:two) -is:reply",
        since_id="10",
        members=(one, two),
    )
    assert command.members == (one, two)
    assert EditorialGroupManifest.model_validate_json(command.model_dump_json()) == command
    for changes in (
        {"query": "from:arbitrary"},
        {"members": (one, one)},
        {"members": (one, two.model_copy(update={"handle": "ONE"}))},
    ):
        with pytest.raises(ValidationError):
            EditorialGroupManifest.model_validate({**command.model_dump(), **changes})


@pytest.mark.parametrize("key", ["body", "raw_text", "html", "markdown", "license", "permissions"])
def test_external_material_metadata_cannot_duplicate_body_or_claim_permission(key):
    with pytest.raises(ValidationError):
        EditorialMaterial(
            url="https://example.com/controlled",
            identity_key="controlled",
            title="Controlled",
            body_status="ok",
            body_text="Official body",
            metadata={"nested": {key: "cannot be another material or licence"}},
        )
