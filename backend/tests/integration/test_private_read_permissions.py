"""Check metadata permission using isolated SQL and controlled storage."""

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from tests.integration.test_private_exports import editorial_client as editorial_client
from tests.integration.test_private_exports import execution, seed

from core.errors import ApplicationError
from evidence.schemas import DeletionReason
from evidence.services import LifecycleService
from jobs.execution import JobExecutionService, MessageReference
from reports.export_execution import PrivateExportExecutor
from reports.export_schemas import ContentExportInput, ReportExportInput
from reports.export_services import PrivateExportService
from reports.models import Report
from reports.schemas import ReportKind
from reports.services import ReportService


class MemoryStorage:
    def __init__(self):
        self.objects = {}
        self.reads = 0

    def check_bucket(self):
        pass

    def put(self, name, body, mime_type):
        self.objects[name] = body

    def get(self, name, *, max_bytes):
        self.reads += 1
        body = self.objects[name]
        assert len(body) <= max_bytes
        return body


@pytest.mark.parametrize("kind", ["report", "content"])
@pytest.mark.parametrize("restriction", ["source", "observation", "expiry"])
def test_export_metadata_obeys_current_frozen_input_permission(editorial_client, kind, restriction):
    owner, report, versions, now = seed(editorial_client)
    sessions = editorial_client.app.state.session_factory
    storage = MemoryStorage()
    editorial_client.app.state.media_storage = storage
    with sessions() as session:
        service = PrivateExportService(session, storage, clock=lambda: now)
        if kind == "report":
            view = service.accept_report(
                owner_id=owner,
                report_id=report.id,
                command=ReportExportInput(operation_id=uuid4(), report_version=1, format="json"),
            )
        else:
            view = service.accept_content(
                owner_id=owner,
                command=ContentExportInput(
                    operation_id=uuid4(), content_version_ids=versions, format="json"
                ),
            )
    message, lease = execution(sessions, view, now)
    completion = PrivateExportExecutor(sessions, storage, clock=lambda: now).execute(message, lease)
    assert completion is not None
    with sessions() as session:
        JobExecutionService(session, lease_seconds=30, clock=lambda: now).complete(
            lease,
            message=MessageReference(message.message_id, "hotkey.jobs", 0, 0),
            completion=completion,
        )
        service = PrivateExportService(session, storage, clock=lambda: now)
        assert service.get(owner_id=owner, export_id=view.id, kind=kind).artifact_size > 0
        with pytest.raises(ApplicationError, match="resource_not_found"):
            service.get(owner_id=uuid4(), export_id=view.id, kind=kind)
    assert editorial_client.get(f"/api/{kind}-exports/{view.id}").status_code == 200
    if restriction == "source":
        with sessions.begin() as session:
            session.execute(
                text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
                {"owner": owner},
            )
    elif restriction == "observation":
        with sessions() as session:
            identity = session.scalar(
                text(
                    "SELECT resource_id FROM evidence_resources WHERE owner_id=:owner "
                    "AND resource_type='content_observation' LIMIT 1"
                ),
                {"owner": owner},
            )
            session.rollback()
            LifecycleService(session, clock=lambda: now).request_deletion(
                owner_id=owner,
                operation_id=uuid4(),
                resource_type="content_observation",
                resource_id=identity,
                reason=DeletionReason.USER_REQUEST,
            )
    check_time = now + timedelta(days=60) if restriction == "expiry" else now
    with sessions() as session, pytest.raises(ApplicationError):
        PrivateExportService(session, storage, clock=lambda: check_time).get(
            owner_id=owner, export_id=view.id, kind=kind
        )
    assert storage.reads == 0
    if restriction != "expiry":
        response = editorial_client.get(f"/api/{kind}-exports/{view.id}")
        assert response.status_code in {403, 404}
        assert (
            not {"content_count", "artifact_size", "artifact_sha256", "input_sha256"}
            & response.json().keys()
        )


def test_report_list_filters_before_pagination_and_rejects_withdrawn_anchor(editorial_client):
    owner, report, _, now = seed(editorial_client)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        original = session.get(Report, report.id)
        template = {
            column.name: deepcopy(getattr(original, column.name))
            for column in Report.__table__.columns
        }
        denied = []
        readable = [report.id]
        for index in range(1, 105):
            identifier = uuid4()
            values = deepcopy(template)
            values.update(
                id=identifier,
                window_start=report.window_start - timedelta(days=index),
                window_end=report.window_end - timedelta(days=index),
            )
            if index < 103:
                denied.append(identifier)
                values["input_manifest"]["observation_ids"] = [str(uuid4())]
            else:
                readable.append(identifier)
            session.add(Report(**values))
    args = dict(
        owner_id=owner,
        topic_id=report.topic_id,
        date_from=None,
        date_to=None,
        kind=ReportKind.DAILY,
        limit=2,
    )
    with sessions() as session:
        service = ReportService(session, clock=lambda: now)
        first, cursor = service.list_reports(**args, cursor=None)
        assert [item.id for item in first] == readable[:2]
        assert cursor == str(readable[1])
        second, cursor = service.list_reports(**args, cursor=readable[1])
        assert [item.id for item in second] == readable[2:]
        assert cursor is None
        with pytest.raises(ApplicationError, match="resource_not_found"):
            service.list_reports(**args, cursor=denied[0])
    with sessions.begin() as session:
        session.execute(
            text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
            {"owner": owner},
        )
    with sessions() as session:
        service = ReportService(session, clock=lambda: now)
        assert service.list_reports(**args, cursor=None) == ([], None)
        with pytest.raises(ApplicationError, match="resource_not_found"):
            service.list_reports(**args, cursor=readable[0])
