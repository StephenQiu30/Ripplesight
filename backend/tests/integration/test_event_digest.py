# ruff: noqa: F811, RUF001
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from tests.integration.test_ai_calls import _enable_ai_budget
from tests.integration.test_event_reading import _seed_reading, event_read_client  # noqa: F401

from ai.models import AiCall
from ai.schemas import AiCompletion, AiTokenUsage
from events.corrections import EventCorrectionService
from events.digest import (
    EventDigestExecutor,
    EventDigestService,
    load_event_digest_input_in_transaction,
)
from events.digest_prompts import LEGACY_DIGEST_PROMPT_VERSION, event_digest_prompt_version
from events.fact_models import EventDerivedContent
from events.fact_schemas import EventCorrectionInput
from events.models import Event
from evidence.schemas import DeletionReason
from evidence.services import LifecycleService
from jobs.execution import JobExecutionFailure, JobExecutionService
from jobs.models import Job, OutboxMessage


def test_manual_revision_enqueues_one_digest_through_existing_job_outbox(
    event_read_client: TestClient,
) -> None:
    owner, _, event_id, fixed, _ = _seed_reading(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        result = EventCorrectionService(session).correct(
            owner_id=owner,
            actor_id=owner,
            command=EventCorrectionInput(
                operation_id=uuid4(),
                kind="split",
                reason="单独核对",
                content_ids=[fixed.id],
                expected_revisions={event_id: 1},
            ),
        )
    with factory() as session, session.begin():
        service = EventDigestService(session)
        assert service.enqueue_due_in_transaction(now=datetime.now(UTC), ai_enabled=True) == 1
        assert service.enqueue_due_in_transaction(now=datetime.now(UTC), ai_enabled=True) == 0
        derived = session.get(EventDerivedContent, (owner, result.target_event_id))
        assert derived.status == "pending" and derived.job_id is not None
        job = session.get(Job, derived.job_id)
        assert job.kind == "events.digest"
        assert (
            session.scalar(select(OutboxMessage).where(OutboxMessage.aggregate_id == job.id))
            is not None
        )


def test_digest_commit_rechecks_revision_and_actual_readable_inputs(
    event_read_client: TestClient,
) -> None:
    owner, _, event_id, _, _ = _seed_reading(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session, session.begin():
        EventDigestService(session).enqueue_due_in_transaction(
            now=datetime.now(UTC), ai_enabled=True
        )
        derived = session.get(EventDerivedContent, (owner, event_id))
        job_id, fingerprint = derived.job_id, derived.input_fingerprint
    with factory() as session, session.begin():
        event = session.get(Event, event_id)
        event.revision += 1
    with factory() as session, session.begin():
        result = EventDigestService(session).commit_in_transaction(
            owner_id=owner,
            event_id=event_id,
            job_id=job_id,
            expected_revision=1,
            expected_fingerprint=fingerprint,
            narrative=SimpleNamespace(title="不得显示", summary="旧模型结果", latest_progress=None),
            ai_call_id=uuid4(),
            now=datetime.now(UTC),
        )
        assert result is False
        derived = session.get(EventDerivedContent, (owner, event_id))
        assert derived.status == "stale" and derived.title is None


class _DigestClient:
    provider = "fake"
    model = "controlled"

    def __init__(self, before_return=None, summary=None):
        self.calls = 0
        self.before_return = before_return
        self.requests = []
        self.summary = (
            summary
            if summary is not None
            else (
                "固定证据支持当前事件的核心变化，归并结果保留原正文与来源的版本关系。"
                "新标题对应同一组已读取材料，概览只用于受控持久化测试，不代表真实模型质量。\n\n"
                "事件成员在提交之前再次复核，许可或人工修订变化会使旧结果失效。"
                "读取继续沿用固定版本，撤回后不再展示由旧材料派生的标题和概览。"
            )
        )

    def complete(self, **_kwargs):
        self.calls += 1
        self.requests.append(_kwargs)
        if self.before_return:
            self.before_return()
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output={
                "title": "固定证据新标题",
                "summary": self.summary,
                "latest_progress": None,
            },
            usage=AiTokenUsage(input_tokens=12, output_tokens=8),
            duration_ms=10,
        )

    def close(self):
        pass


def _enqueue_message(client, owner, event_id):
    factory = client.app.state.session_factory
    with factory() as session, session.begin():
        EventDigestService(session).enqueue_due_in_transaction(
            now=datetime.now(UTC), ai_enabled=True
        )
        derived = session.get(EventDerivedContent, (owner, event_id))
        job = session.get(Job, derived.job_id)
        return SimpleNamespace(
            kind=job.kind,
            job_id=job.id,
            owner_id=owner,
            operation_id=job.operation_id,
            configuration_ref=job.configuration_ref,
            configuration_version=job.configuration_version,
        )


def test_digest_executor_uses_real_ai_budget_ledger_and_withdrawal_hides_valid_text(
    event_read_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, _, event_id, fixed, _ = _seed_reading(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        _enable_ai_budget(session.get_bind(), owner)
    message = _enqueue_message(event_read_client, owner, event_id)
    fake = _DigestClient()
    monkeypatch.setattr("events.digest.create_ai_client", lambda _settings: fake)
    executor = EventDigestExecutor(
        factory,
        event_read_client.app.state.settings.model_copy(
            update={"events_cluster_enabled": True, "ai_enabled": True}
        ),
    )
    executor.execute(message)
    executor.execute(message)
    assert fake.calls == 1
    with factory() as session:
        call = session.scalar(select(AiCall))
        assert call.purpose == "events.digest" and call.job_id == message.job_id
        assert call.prompt_version == event_digest_prompt_version()
        derived = session.get(EventDerivedContent, (owner, event_id))
        assert derived.ai_call_id == call.id and derived.summary == fake.summary
        job = session.get(Job, message.job_id)
        assert job.scope["prompt_version"] == call.prompt_version
        assert '"prompt_version"' in job.scope["input_manifest"]
        assert "事件概览" in fake.requests[0]["prompt"]
        assert call.input_tokens == 12
        assert session.execute(
            text("SELECT sum(used_units),sum(reserved_units) FROM resource_budget_windows")
        ).one() == (1, 0)
    detail = event_read_client.get(f"/api/events/{event_id}").json()
    assert detail["title"] == "固定证据新标题" and detail["derived_text_available"]
    with factory() as session:
        LifecycleService(session).request_deletion(
            owner_id=owner,
            operation_id=uuid4(),
            resource_type="content_observation",
            resource_id=fixed.latest_observation.id,
            reason=DeletionReason.USER_REQUEST,
        )
    assert event_read_client.get(f"/api/events/{event_id}").status_code == 404


def test_late_digest_model_does_not_override_a_manual_revision(
    event_read_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, _, event_id, fixed, _ = _seed_reading(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        _enable_ai_budget(session.get_bind(), owner)
    message = _enqueue_message(event_read_client, owner, event_id)

    def split_during_model():
        with factory() as session:
            EventCorrectionService(session).correct(
                owner_id=owner,
                actor_id=owner,
                command=EventCorrectionInput(
                    operation_id=uuid4(),
                    kind="split",
                    reason="模型期间修订",
                    expected_revisions={event_id: 1},
                    content_ids=[fixed.id],
                ),
            )

    fake = _DigestClient(before_return=split_during_model)
    monkeypatch.setattr("events.digest.create_ai_client", lambda _settings: fake)
    with pytest.raises(JobExecutionFailure, match="event_digest_input_changed"):
        EventDigestExecutor(
            factory,
            event_read_client.app.state.settings.model_copy(
                update={"events_cluster_enabled": True, "ai_enabled": True}
            ),
        ).execute(message)
    with factory() as session:
        assert session.get(EventDerivedContent, (owner, event_id)).title is None
        assert session.scalar(select(AiCall)).status == "succeeded"
    detail = event_read_client.get(f"/api/events/{event_id}").json()
    assert detail["title"] is None and not detail["derived_text_available"]


@pytest.mark.parametrize("change", ["permission", "manual_revision"])
def test_digest_final_admission_rechecks_after_prepare_before_ai(
    event_read_client, monkeypatch, change
):
    owner, _, event_id, fixed, _ = _seed_reading(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        _enable_ai_budget(session.get_bind(), owner)
    message = _enqueue_message(event_read_client, owner, event_id)
    with factory() as session:
        lease = JobExecutionService(session, lease_seconds=300).acquire(
            job_id=message.job_id, worker_id="controlled-digest-admission"
        )
        calls = session.execute(text("SELECT count(*) FROM ai_calls")).scalar()
        reservations = session.execute(
            text("SELECT count(*) FROM resource_budget_reservations")
        ).scalar()
    provider = _DigestClient()

    def change_after_prepare(_):
        with factory() as session:
            if change == "permission":
                with session.begin():
                    session.execute(text("UPDATE source_access_policies SET enabled=false"))
            else:
                EventCorrectionService(session).correct(
                    owner_id=owner,
                    actor_id=owner,
                    command=EventCorrectionInput(
                        operation_id=uuid4(),
                        kind="split",
                        reason="准入前人工修订",
                        expected_revisions={event_id: 1},
                        content_ids=[fixed.id],
                    ),
                )
        return provider

    monkeypatch.setattr("events.digest.create_ai_client", change_after_prepare)
    with pytest.raises(JobExecutionFailure, match="event_digest_input_changed"):
        EventDigestExecutor(
            factory,
            event_read_client.app.state.settings.model_copy(
                update={"events_cluster_enabled": True, "ai_enabled": True}
            ),
        ).execute(message, lease)
    assert provider.calls == 0
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar() == calls
        assert (
            session.execute(text("SELECT count(*) FROM resource_budget_reservations")).scalar()
            == reservations
        )


def test_digest_lost_response_does_not_call_paid_model_again(event_read_client, monkeypatch):
    owner, _, event_id, _, _ = _seed_reading(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        _enable_ai_budget(session.get_bind(), owner)
    message = _enqueue_message(event_read_client, owner, event_id)
    fake = _DigestClient()
    monkeypatch.setattr("events.digest.create_ai_client", lambda _settings: fake)
    original_commit = EventDigestService.commit_in_transaction
    monkeypatch.setattr(
        EventDigestService,
        "commit_in_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SystemExit()),
    )
    executor = EventDigestExecutor(
        factory,
        event_read_client.app.state.settings.model_copy(
            update={"events_cluster_enabled": True, "ai_enabled": True}
        ),
    )
    with pytest.raises(SystemExit):
        executor.execute(message)
    monkeypatch.setattr(EventDigestService, "commit_in_transaction", original_commit)
    with pytest.raises(JobExecutionFailure, match="event_digest_result_unknown") as failure:
        executor.execute(message)
    assert not failure.value.manual_retry_allowed
    assert fake.calls == 1
    with factory() as session:
        derived = session.get(EventDerivedContent, (owner, event_id))
        assert derived.status == "failed" and derived.error_code == "result_unknown"
        assert derived.title is None


@pytest.mark.parametrize(
    "summary",
    [
        "过短",
        "甲" * 151 + "\n\n" + "乙" * 150,
        "甲" * 150,
        "首先，" + "甲" * 60 + "\n\n" + "乙" * 60,
    ],
    ids=["short", "long", "unsegmented", "timeline-first"],
)
def test_digest_invalid_output_keeps_receipt_and_clears_derived_text(
    event_read_client, monkeypatch, summary
):
    owner, _, event_id, _, _ = _seed_reading(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        _enable_ai_budget(session.get_bind(), owner)
    message = _enqueue_message(event_read_client, owner, event_id)
    fake = _DigestClient(summary=summary)
    monkeypatch.setattr("events.digest.create_ai_client", lambda _settings: fake)
    executor = EventDigestExecutor(
        factory,
        event_read_client.app.state.settings.model_copy(
            update={"events_cluster_enabled": True, "ai_enabled": True}
        ),
    )
    with pytest.raises(JobExecutionFailure, match="event_digest_invalid_model_output"):
        executor.execute(message)
    with factory() as session:
        derived = session.get(EventDerivedContent, (owner, event_id))
        assert derived.status == "failed" and derived.error_code == "invalid_model_output"
        assert derived.title is derived.summary is derived.latest_progress is None
        call = session.get(AiCall, derived.ai_call_id)
        assert call.job_id == message.job_id
        assert call.prompt_version == event_digest_prompt_version()
    assert not event_read_client.get(f"/api/events/{event_id}").json()["derived_text_available"]


def test_legacy_digest_is_readable_without_new_length_or_template_rules(
    event_read_client, monkeypatch
):
    owner, _, event_id, _, _ = _seed_reading(event_read_client)
    factory = event_read_client.app.state.session_factory
    with factory() as session:
        _enable_ai_budget(session.get_bind(), owner)
    message = _enqueue_message(event_read_client, owner, event_id)
    monkeypatch.setattr("events.digest.create_ai_client", lambda _settings: _DigestClient())
    EventDigestExecutor(
        factory,
        event_read_client.app.state.settings.model_copy(
            update={"events_cluster_enabled": True, "ai_enabled": True}
        ),
    ).execute(message)
    with factory() as session, session.begin():
        event = session.get(Event, event_id)
        inputs = load_event_digest_input_in_transaction(
            session,
            event=event,
            now=datetime.now(UTC),
            prompt_version=LEGACY_DIGEST_PROMPT_VERSION,
            render_prompt=False,
        )
        assert inputs is not None
        derived = session.get(EventDerivedContent, (owner, event_id))
        derived.input_fingerprint = inputs.fingerprint
        derived.summary = event.summary = "旧版短摘要保持可读"
        call = session.get(AiCall, derived.ai_call_id)
        call.prompt_version = LEGACY_DIGEST_PROMPT_VERSION
        job = session.get(Job, message.job_id)
        scope = dict(job.scope)
        scope.pop("prompt_version")
        scope["input_fingerprint"] = inputs.fingerprint.hex()
        job.scope = scope
    detail = event_read_client.get(f"/api/events/{event_id}").json()
    assert detail["derived_text_available"] and detail["summary"] == "旧版短摘要保持可读"


def test_digest_template_change_after_enqueue_is_rejected_before_ai(event_read_client, monkeypatch):
    owner, _, event_id, _, _ = _seed_reading(event_read_client)
    message = _enqueue_message(event_read_client, owner, event_id)
    fake = _DigestClient()
    monkeypatch.setattr("events.digest.create_ai_client", lambda _settings: fake)
    monkeypatch.setattr("events.digest.event_digest_prompt_version", lambda: "story-digest@changed")
    with pytest.raises(JobExecutionFailure, match="event_digest_input_changed"):
        EventDigestExecutor(
            event_read_client.app.state.session_factory,
            event_read_client.app.state.settings.model_copy(
                update={"events_cluster_enabled": True}
            ),
        ).execute(message)
    assert fake.calls == 0
