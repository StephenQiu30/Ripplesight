import json
from collections.abc import Callable, Iterator, Mapping
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration import test_editorial_execution as editorial_fixture
from tests.integration.test_content_search import _seed_posts
from tests.integration.test_editorial_execution import (
    ControlledClient,
    _budget,
    _execute,
    _source,
)
from tests.integration.test_editorial_execution import editorial_client as _editorial_client

from ai.schemas import AiCompletion, AiTokenUsage
from ai.services import AiService
from analysis import translation_services as translation_module
from analysis.editorial_schemas import EditorialRunInput
from analysis.editorial_services import EditorialService
from analysis.translation_schemas import TranslationRequestInput, TranslationRunView
from analysis.translation_services import ContentTranslationExecutor, ContentTranslationService
from jobs.execution import (
    ExecutionLease,
    JobExecutionService,
    JobLeaseUnavailableError,
    StaleExecutionLeaseError,
)
from jobs.schemas import JobAcceptedMessage, JobStatus
from jobs.services import JobService
from publication.schemas import SourcePolicyInput
from publication.services import PublicationService


@pytest.fixture
def editorial_client() -> Iterator[TestClient]:
    yield from _editorial_client.__wrapped__()


class LongTranslationClient:
    provider = "controlled"
    model = "controlled-editorial"

    def __init__(self, callback: Callable[[], None] | None = None) -> None:
        self.calls = 0
        self.callback = callback

    def complete(
        self, *, prompt: str, output_schema: Mapping[str, Any], instructions: str = ""
    ) -> AiCompletion:
        self.calls += 1
        if self.callback:
            callback, self.callback = self.callback, None
            callback()
        fragments = json.loads(prompt)["fragments"]
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output={"t": [f"受控中文段落 {self.calls}-{index}" for index in range(len(fragments))]},
            usage=AiTokenUsage(input_tokens=100, output_tokens=20),
            duration_ms=1,
        )


def _message(client: TestClient, job_id: UUID) -> tuple[JobAcceptedMessage, ExecutionLease]:
    with client.app.state.session_factory() as session:
        event = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": job_id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {
                **event.payload,
                "message_id": event.id,
                "event_type": event.event_type,
                "schema_version": 2,
            }
        )
        lease = JobExecutionService(
            session, lease_seconds=30, clock=lambda: editorial_fixture.NOW
        ).acquire(job_id=job_id, worker_id="controlled-translation-recovery")
    return message, lease


def _admit(
    client: TestClient, count: int
) -> tuple[UUID, TranslationRunView, JobAcceptedMessage, ExecutionLease]:
    body = "\n\n".join(f"{'a' * 3000} {index}" for index in range(count))
    owner, _, posts = _seed_posts(client, [("OpenAI new model", body)])
    _source(client, owner)
    _budget(client, owner)
    version = posts[0].latest_observation.content_version
    assert version is not None
    sessions = client.app.state.session_factory
    with sessions() as session:
        editorial = EditorialService(session, clock=lambda: editorial_fixture.NOW).request_run(
            owner_id=owner,
            content_id=posts[0].id,
            source_key="x",
            command=EditorialRunInput(operation_id=uuid4(), content_version_id=version.id),
        )
    assert editorial.job_id is not None
    message, lease = _message(client, editorial.job_id)
    _execute(client, owner, message, lease, ControlledClient())
    with sessions.begin() as session:
        service = PublicationService(session)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=editorial_fixture.NOW,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                site_fulltext=True,
                release_delay_seconds=0,
                license_name="受控许可",
                reason="完整长正文翻译验收",
            ),
        )
        service.publish_in_transaction(
            owner_id=owner, content_id=posts[0].id, now=editorial_fixture.NOW
        )
    with sessions() as session:
        run = ContentTranslationService(session, clock=lambda: editorial_fixture.NOW).request(
            owner_id=owner,
            content_id=posts[0].id,
            command=TranslationRequestInput(
                operation_id=uuid4(),
                content_version_id=version.id,
                policy_revision=1,
                reason="多批次恢复与取消验收",
            ),
        )
    assert run.job_id is not None
    message, lease = _message(client, run.job_id)
    return owner, run, message, lease


def test_saved_multibatch_receipts_resume_after_crash_with_new_lease_without_repaying(
    editorial_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, run, message, lease = _admit(editorial_client, 3)
    sessions = editorial_client.app.state.session_factory
    provider = LongTranslationClient()
    original = translation_module.assemble_translation

    def interrupt(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt("after durable batch answers, before business body")

    monkeypatch.setattr(translation_module, "assemble_translation", interrupt)
    with sessions() as ai_session, pytest.raises(KeyboardInterrupt):
        ContentTranslationExecutor(
            sessions, editorial_client.app.state.settings, clock=lambda: editorial_fixture.NOW
        ).execute(
            message,
            lease,
            ai=AiService(ai_session, provider, clock=lambda: editorial_fixture.NOW),
        )
    assert provider.calls == 3
    with sessions() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM content_translation_batches WHERE status='succeeded'")
            ).scalar_one()
            == 3
        )
        assert (
            session.execute(text("SELECT body_html FROM content_translation_runs")).scalar_one()
            is None
        )
        recovered_at = editorial_fixture.NOW + timedelta(seconds=31)
        recovered_lease = JobExecutionService(
            session, lease_seconds=30, clock=lambda: recovered_at
        ).acquire(
            job_id=message.job_id,
            worker_id="controlled-recovered-translation",
        )
    assert recovered_lease.epoch == lease.epoch + 1
    monkeypatch.setattr(translation_module, "assemble_translation", original)
    executor = ContentTranslationExecutor(
        sessions, editorial_client.app.state.settings, clock=lambda: recovered_at
    )
    with sessions() as ai_session:
        ai = AiService(ai_session, provider, clock=lambda: recovered_at)
        with pytest.raises(StaleExecutionLeaseError):
            executor.execute(message, lease, ai=ai)
        assert executor.execute(message, recovered_lease, ai=ai).status == JobStatus.SUCCEEDED
        assert executor.execute(message, recovered_lease, ai=ai).status == JobStatus.SUCCEEDED
    assert provider.calls == 3
    with sessions() as session:
        view = ContentTranslationService(session, clock=lambda: recovered_at).get(
            owner_id=owner, run_id=run.id
        )
        assert view.complete and view.translated_segments == 3 and view.total_segments == 3
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 8


def test_translation_cap_preserves_entire_original_tail_and_reports_partial(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _admit(editorial_client, 25)
    sessions = editorial_client.app.state.session_factory
    provider = LongTranslationClient()
    with sessions() as ai_session:
        assert (
            ContentTranslationExecutor(
                sessions, editorial_client.app.state.settings, clock=lambda: editorial_fixture.NOW
            )
            .execute(
                message,
                lease,
                ai=AiService(ai_session, provider, clock=lambda: editorial_fixture.NOW),
            )
            .status
            == JobStatus.SUCCEEDED
        )
    with sessions() as session:
        view = ContentTranslationService(session, clock=lambda: editorial_fixture.NOW).get(
            owner_id=owner, run_id=run.id
        )
        assert view.status == "partial" and not view.complete
        assert view.translated_segments == 19 and view.total_segments == 25
        assert view.body_html and "a" * 3000 + " 24" in view.body_html
        assert provider.calls == 19


def test_translation_cancel_after_first_response_stops_remaining_paid_batches(
    editorial_client: TestClient,
) -> None:
    owner, run, message, lease = _admit(editorial_client, 3)
    sessions = editorial_client.app.state.session_factory

    def cancel() -> None:
        with sessions() as session:
            JobService(session, clock=lambda: editorial_fixture.NOW).request_cancel(
                owner_id=owner, job_id=message.job_id
            )

    provider = LongTranslationClient(cancel)
    with sessions() as ai_session, pytest.raises(JobLeaseUnavailableError):
        ContentTranslationExecutor(
            sessions, editorial_client.app.state.settings, clock=lambda: editorial_fixture.NOW
        ).execute(
            message,
            lease,
            ai=AiService(ai_session, provider, clock=lambda: editorial_fixture.NOW),
        )
    assert provider.calls == 1
    with sessions() as session:
        view = ContentTranslationService(session, clock=lambda: editorial_fixture.NOW).get(
            owner_id=owner, run_id=run.id
        )
        assert (
            view.status == "failed"
            and view.reason == "translation_cancelled"
            and view.body_html is None
        )
        assert (
            session.execute(
                text("SELECT count(*) FROM content_translation_batches WHERE status='succeeded'")
            ).scalar_one()
            == 1
        )
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 6
