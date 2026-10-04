"""Current database facts override held ORM images during independent bulk ALL reads."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from tests.integration.test_analysis_observation_inputs import aliases, freeze
from tests.integration.test_editorial_source_profiles import engine as engine
from tests.unit.test_editorial_native_identity import NOW

from content.analysis_inputs import analysis_observation_manifests_readable_in_transaction
from content.models import ContentObservation, ContentVisibilityObservation
from content.observation_inputs import freeze_observation_inputs_in_transaction
from core.errors import ApplicationError
from evidence.models import EvidenceResource


@pytest.mark.parametrize("correction", ["visibility", "graph", "evidence"])
def test_bulk_and_singleton_immediately_read_corrected_current_facts_without_expire(
    engine, correction
):
    with Session(engine, expire_on_commit=False) as session:
        owner, _, _, a, b = aliases(session)
        with session.begin():
            read_at = NOW + timedelta(seconds=1)
            manifest_a, manifest_b = freeze(session, owner, a), freeze(session, owner, b)
            observation = session.get(ContentObservation, a[2])
            if correction == "visibility":
                held = ContentVisibilityObservation(
                    id=uuid4(),
                    owner_id=owner,
                    content_id=a[0],
                    job_id=observation.job_id,
                    source_operation_id=uuid4(),
                    status="visible",
                    basis="content_returned",
                    observed_at=read_at,
                    received_at=read_at,
                )
                session.add(held)
                session.flush()
            elif correction == "graph":
                held = observation
            else:
                held = session.scalar(
                    select(EvidenceResource).where(
                        EvidenceResource.owner_id == owner,
                        EvidenceResource.resource_type == "content_observation",
                        EvidenceResource.resource_id == a[2],
                    )
                )
            before = analysis_observation_manifests_readable_in_transaction(
                session, owner_id=owner, manifests=(manifest_a, manifest_b), now=read_at
            )
            assert before == {manifest_a.signature: True, manifest_b.signature: True}
            assert freeze_observation_inputs_in_transaction(
                session, owner_id=owner, observation_ids=(a[2],), now=read_at
            ) == (a[2],)
            if correction == "visibility":
                session.execute(
                    text(
                        "UPDATE content_visibility_observations "
                        "SET status='deleted',basis='source_tombstone' WHERE id=:id"
                    ),
                    {"id": held.id},
                )
            elif correction == "graph":
                session.execute(
                    text(
                        "UPDATE content_observations SET input_basis='observations_v1' WHERE id=:id"
                    ),
                    {"id": held.id},
                )
            else:
                session.execute(
                    text(
                        "UPDATE evidence_resources "
                        "SET source_policy_version=source_policy_version+1 WHERE id=:id"
                    ),
                    {"id": held.id},
                )
            # No expire()/new Session: each call must read the corrected database fact.
            after = analysis_observation_manifests_readable_in_transaction(
                session, owner_id=owner, manifests=(manifest_a, manifest_b), now=read_at
            )
            assert after == {manifest_a.signature: False, manifest_b.signature: True}
            with pytest.raises(ApplicationError, match="editorial_material_unavailable"):
                freeze_observation_inputs_in_transaction(
                    session, owner_id=owner, observation_ids=(a[2],), now=read_at
                )
            assert freeze_observation_inputs_in_transaction(
                session, owner_id=owner, observation_ids=(b[2],), now=read_at
            ) == (b[2],)
