from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_editorial_execution import editorial_client as _editorial_client
from tests.integration.test_report_editions import _admit

from ai.schemas import AiCallError, AiCompletion, AiFailureCode, AiTokenUsage
from ai.services import AiService
from analysis.translation_schemas import TranslationRequestInput
from analysis.translation_services import ContentTranslationExecutor, ContentTranslationService
from core.errors import ApplicationError
from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.schemas import JobAcceptedMessage, JobStatus
from publication.schemas import SourcePolicyInput
from publication.services import PublicationService


@pytest.fixture
def editorial_client() -> Iterator[TestClient]:
    yield from _editorial_client.__wrapped__()


class TranslationClient:
    provider = "controlled"
    model = "controlled-editorial"

    def __init__(self, callback: Callable[[], None] | None = None) -> None:
        self.calls = 0
        self.failure: AiFailureCode | None = None
        self.callback = callback

    def complete(
        self, *, prompt: str, output_schema: Mapping[str, Any], instructions: str = ""
    ) -> AiCompletion:
        self.calls += 1
        if self.callback:
            self.callback()
        if self.failure:
            raise AiCallError(self.failure, "controlled translation")
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output={"t": ["OpenAI 发布新模型并公开 API。"]},
            usage=AiTokenUsage(input_tokens=100, output_tokens=20),
            duration_ms=1,
        )


@pytest.mark.parametrize("case", ["complete", "timeout", "revoke"])
def test_translation_fixed_permission_receipt_and_no_repayment(
    editorial_client: TestClient, case: str
) -> None:
    owner, edition, _, _ = _admit(editorial_client)
    sessions = editorial_client.app.state.session_factory
    now = edition.window_end + timedelta(hours=2)
    with sessions.begin() as session:
        PublicationService(session).save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=now,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=1,
                participation_mode="editorial",
                site_fulltext=True,
                license_name="受控全文",
                reason="受控翻译",
            ),
        )
        content_id, version_id = session.execute(
            text("SELECT content_id,content_version_id FROM editorial_runs")
        ).one()
        PublicationService(session).publish_in_transaction(
            owner_id=owner, content_id=content_id, now=now
        )
    with sessions() as session:
        service = ContentTranslationService(session, clock=lambda: now)
        command = TranslationRequestInput(
            operation_id=uuid4(),
            content_version_id=version_id,
            policy_revision=2,
            reason="译文验收",
        )
        run = service.request(owner_id=owner, content_id=content_id, command=command)
        assert service.request(owner_id=owner, content_id=content_id, command=command).id == run.id
    with sessions() as session:
        event = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": run.job_id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {
                **event.payload,
                "message_id": event.id,
                "event_type": event.event_type,
                "schema_version": 2,
            }
        )
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: now).acquire(
            job_id=run.job_id, worker_id="controlled-translation"
        )

    def revoke() -> None:
        with sessions.begin() as session:
            PublicationService(session).save_source_policy_in_transaction(
                owner_id=owner,
                actor_id=owner,
                source_key="x",
                now=now,
                command=SourcePolicyInput(
                    operation_id=uuid4(),
                    expected_revision=2,
                    participation_mode="editorial",
                    license_name="收紧许可",
                    reason="译文撤回",
                ),
            )

    client = TranslationClient(revoke if case == "revoke" else None)
    if case == "timeout":
        client.failure = AiFailureCode.TIMEOUT
    executor = ContentTranslationExecutor(
        sessions, editorial_client.app.state.settings, clock=lambda: now
    )
    with sessions() as ai_session:
        ai = AiService(ai_session, client, clock=lambda: now)
        if case == "complete":
            assert executor.execute(message, lease, ai=ai).status == JobStatus.SUCCEEDED
            assert executor.execute(message, lease, ai=ai).status == JobStatus.SUCCEEDED
            with sessions() as cached_session:
                service = ContentTranslationService(cached_session, clock=lambda: now)
                cached_command = command.model_copy(update={"operation_id": uuid4()})
                cached = service.request(
                    owner_id=owner, content_id=content_id, command=cached_command
                )
                assert cached.id == run.id and cached.job_id != run.job_id
                assert (
                    service.request(
                        owner_id=owner, content_id=content_id, command=cached_command
                    ).job_id
                    == cached.job_id
                )
                with pytest.raises(ApplicationError, match="idempotency_conflict"):
                    service.request(
                        owner_id=owner,
                        content_id=content_id,
                        command=cached_command.model_copy(update={"reason": "changed payload"}),
                    )
            with sessions() as cached_session:
                cached_event = cached_session.execute(
                    text(
                        "SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"
                    ),
                    {"job": cached.job_id},
                ).one()
                cached_message = JobAcceptedMessage.model_validate(
                    {
                        **cached_event.payload,
                        "message_id": cached_event.id,
                        "event_type": cached_event.event_type,
                        "schema_version": 2,
                    }
                )
                cached_lease = JobExecutionService(
                    cached_session, lease_seconds=30, clock=lambda: now
                ).acquire(job_id=cached.job_id, worker_id="controlled-cached-translation")
            assert (
                executor.execute(cached_message, cached_lease, ai=ai).status == JobStatus.SUCCEEDED
            )
        else:
            for _ in range(2):
                with pytest.raises(JobExecutionFailure, match="translation_"):
                    executor.execute(message, lease, ai=ai)
    assert client.calls == 1
    with sessions() as session:
        view = ContentTranslationService(session, clock=lambda: now).get(
            owner_id=owner, run_id=run.id
        )
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 6
        assert (
            session.execute(text("SELECT count(*) FROM content_translation_runs")).scalar_one() == 1
        )
        assert session.execute(
            text("SELECT ai_call_id IS NOT NULL FROM content_translation_batches")
        ).scalar_one()
        if case == "complete":
            assert view.complete and view.body_html and view.status == "complete"
        elif case == "timeout":
            assert view.status == "unknown" and view.body_html is None
        else:
            assert view.status == "stale" and view.body_html is None
