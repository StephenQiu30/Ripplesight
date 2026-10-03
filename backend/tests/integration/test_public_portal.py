from uuid import uuid4

from fastapi.testclient import TestClient
from tests.conftest import authenticate_test_client
from tests.integration.test_publication import (
    NOW,
    ControlledClient,
    _budget,
    _execute,
    _run,
)
from tests.integration.test_publication import (
    editorial_client as editorial_client,
)

from publication.schemas import SourcePolicyInput
from publication.services import PublicationService


def test_anonymous_publication_uses_only_the_designated_publisher_and_current_permission(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _run(editorial_client)
    _budget(editorial_client, owner)
    _execute(editorial_client, owner, message, lease, ControlledClient())
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        service = PublicationService(session)
        policy = service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                release_delay_seconds=0,
                license_name="Controlled public license",
                reason="Explicit public publisher acceptance",
            ),
            now=NOW,
        )
        service.publish_in_transaction(owner_id=owner, content_id=run.content_id, now=NOW)

    editorial_client.cookies.clear()
    path = "/api/publication/items?mode=all&window=7d"
    anonymous = editorial_client.get(path)
    assert anonymous.status_code == 200, anonymous.text
    assert [item["id"] for item in anonymous.json()["items"]] == [str(run.content_id)]
    assert editorial_client.get("/api/reports").status_code == 401
    assert editorial_client.get("/api/topics").status_code == 401

    # Another visitor's valid account does not switch the public feed's partition.
    visitor = authenticate_test_client(editorial_client)
    assert visitor != owner
    assert editorial_client.get(path).json()["items"] == anonymous.json()["items"]
    assert editorial_client.get("/api/contents").json()["items"] == []
    editorial_client.cookies.clear()

    with sessions.begin() as session:
        service = PublicationService(session)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=policy.revision,
                participation_mode="isolated",
                license_name="Withdrawn controlled public license",
                reason="Revoke public permission",
            ),
            now=NOW,
        )
    assert editorial_client.get(path).json()["items"] == []
    assert editorial_client.get(f"/api/publication/items/{run.content_id}/site").status_code == 404
