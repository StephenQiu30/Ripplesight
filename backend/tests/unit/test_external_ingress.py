from uuid import uuid4

import pytest
from pydantic import ValidationError

from connections.editorial_schemas import ExternalEditorialInput, ExternalIngressItem
from connections.external_ingress import same_batch_duplicate_receipt
from sources.editorial_schemas import EditorialMaterial


def test_external_batch_rejects_more_than_fifty_items_before_admission():
    material = EditorialMaterial(
        url="https://example.com/post", identity_key="controlled-post", title="Controlled material"
    )
    command = dict(
        operation_id=uuid4(),
        expected_revision=1,
        configuration_version=1,
        materials=(material,) * 50,
    )
    assert len(ExternalEditorialInput.model_validate(command).materials) == 50
    with pytest.raises(ValidationError):
        ExternalEditorialInput.model_validate({**command, "materials": (material,) * 51})


def test_duplicate_input_never_claims_a_rejected_original_was_stored():
    duplicate = ExternalIngressItem(index=1, status="duplicate", duplicate_of=0)
    original = ExternalIngressItem(index=0, status="rejected", reason="invalid_material")
    resolved = same_batch_duplicate_receipt(duplicate, original)
    assert resolved.status == "rejected" and resolved.reason == "invalid_material"
    assert resolved.content_id is None and resolved.content_version_id is None
    pending = same_batch_duplicate_receipt(
        duplicate, original.model_copy(update={"status": "pending", "reason": None})
    )
    assert pending.status == "duplicate" and pending.reason == "duplicate_input_pending"
    assert pending.content_id is None
