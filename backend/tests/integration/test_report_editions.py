from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_content_search import _seed_posts
from tests.integration.test_editorial_execution import (
    ControlledClient,
    _budget,
    _execute,
    _request_run,
    _run,
    _source,
)
from tests.integration.test_editorial_execution import editorial_client as _editorial_client

from ai.schemas import AiCallError, AiCompletion, AiFailureCode, AiTokenUsage
from ai.services import AiService
from core.errors import ApplicationError
from jobs.execution import ExecutionLease, JobExecutionFailure, JobExecutionService
from jobs.schemas import JobAcceptedMessage, JobStatus
from publication.schemas import SourcePolicyInput
from publication.services import PublicationService
from reports.edition_reading import load_current_edition_in_transaction
from reports.edition_rules import EditionKind, period_window
from reports.edition_schemas import EditionCorrectionInput, EditionDetailView, EditionRequestInput
from reports.edition_services import EditionExecutor, EditionService

NOW = datetime(2026, 10, 1, 9, tzinfo=UTC)


@pytest.fixture
def editorial_client() -> Iterator[TestClient]:
    yield from _editorial_client.__wrapped__()


class ReportClient:
    provider = "controlled"
    model = "controlled-editorial"

    def __init__(self, callback: Callable[[], None] | None = None) -> None:
        self.calls = 0
        self.callback = callback
        self.failure: AiFailureCode | None = None

    def complete(
        self, *, prompt: str, output_schema: Mapping[str, Any], instructions: str = ""
    ) -> AiCompletion:
        self.calls += 1
        if self.callback:
            self.callback()
        if self.failure:
            raise AiCallError(self.failure, "controlled report failure")
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output={
                "overview": "这一完整刊期发布了模型。",
                "sections": {},
            },
            usage=AiTokenUsage(input_tokens=50, output_tokens=20),
            duration_ms=1,
        )


def _admit(
    client: TestClient,
    *,
    kind: EditionKind = "daily",
    candidate_count: int = 1,
) -> tuple[UUID, EditionDetailView, JobAcceptedMessage, ExecutionLease]:
    # Freeze receipt, analysis, publication and budget clocks together. Imported NOW
    # values otherwise outlive the upstream fixture's per-test clock in a full suite.
    owner, _, posts = _seed_posts(
        client,
        [("OpenAI new model", "OpenAI 发布新模型,公开 API。")] * candidate_count,
        now=NOW,
        dated=True,
    )
    _source(client, owner, now=NOW)
    _budget(client, owner, now=NOW)
    for post in posts:
        _, _, message, lease = _request_run(client, owner, post, now=NOW)
        _execute(client, owner, message, lease, ControlledClient(), now=NOW)
    sessions = client.app.state.session_factory
    with sessions.begin() as session:
        # The controlled monthly window can end 31 days ahead; keep its fixture licensed.
        if kind != "daily":
            session.execute(
                text(
                    "UPDATE evidence_retention_policies SET requested_days=60,effective_days=60 "
                    "WHERE owner_id=:owner"
                ),
                {"owner": owner},
            )
            session.execute(
                text(
                    "UPDATE evidence_resources SET expires_at=collected_at+interval '60 days' "
                    "WHERE owner_id=:owner"
                ),
                {"owner": owner},
            )
        service = PublicationService(session)
        service.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                license_name="受控许可",
                reason="受控刊期输入",
            ),
        )
        for post in posts:
            service.publish_in_transaction(owner_id=owner, content_id=post.id, now=NOW)
    key = NOW.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    _, end = period_window("daily", key)
    at = end + timedelta(hours=2)
    with sessions() as session:
        edition = EditionService(session, clock=lambda: at).request(
            owner_id=owner,
            actor_id=owner,
            command=EditionRequestInput(
                operation_id=uuid4(),
                kind="daily",
                key=key,
                expected_revision=0,
                reason="测试完整自然日",
            ),
        )
    if kind != "daily":
        body, lease = _edition_lease(client, edition, at)
        _executor(client, edition).execute(body, lease)
        local = NOW.astimezone(ZoneInfo("Asia/Shanghai"))
        year, week, _ = local.isocalendar()
        key = f"{year:04}-W{week:02}" if kind == "weekly" else local.strftime("%Y-%m")
        _, end = period_window(kind, key)
        at = end + timedelta(hours=2)
        with sessions() as session:
            edition = EditionService(session, clock=lambda: at).request(
                owner_id=owner,
                actor_id=owner,
                command=EditionRequestInput(
                    operation_id=uuid4(),
                    kind=kind,
                    key=key,
                    expected_revision=0,
                    reason="汇编有效日报",
                ),
            )
    body, lease = _edition_lease(client, edition, at)
    return owner, edition, body, lease


def _edition_lease(
    client: TestClient,
    edition: EditionDetailView,
    at: datetime,
) -> tuple[JobAcceptedMessage, ExecutionLease]:
    sessions = client.app.state.session_factory
    with sessions() as session:
        outbox = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": edition.job_id},
        ).one()
        body = JobAcceptedMessage.model_validate(
            {
                **outbox.payload,
                "message_id": outbox.id,
                "event_type": outbox.event_type,
                "schema_version": 2,
            }
        )
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: at).acquire(
            job_id=edition.job_id, worker_id="controlled-report"
        )
    return body, lease


def _executor(client: TestClient, edition: EditionDetailView) -> EditionExecutor:
    return EditionExecutor(
        client.app.state.session_factory,
        client.app.state.settings,
        clock=lambda: edition.window_end + timedelta(hours=2),
    )


def test_template_report_replay_and_immutable_manual_revision(editorial_client: TestClient) -> None:
    owner, edition, message, lease = _admit(editorial_client)
    executor = _executor(editorial_client, edition)
    assert executor.execute(message, lease).status == JobStatus.SUCCEEDED
    assert executor.execute(message, lease).status == JobStatus.SUCCEEDED
    sessions = editorial_client.app.state.session_factory
    with sessions() as session:
        service = EditionService(session, clock=lambda: edition.window_end + timedelta(hours=2))
        view = service.get(owner_id=owner, edition_id=edition.id)
        assert view.valid and view.content and view.body_markdown
        assert view.generator == "template" and view.ai_call_id is None
        command = EditionCorrectionInput(
            operation_id=uuid4(),
            expected_revision=1,
            title="人工刊期修订",
            lead="人工核对引用。",
            highlights=[view.content.entries[0].content_id],
            themes=[],
            reason="人工纠错",
        )
        corrected = service.correct(
            owner_id=owner, actor_id=owner, edition_id=view.id, command=command
        )
        assert corrected.revision == 2 and corrected.generator == "manual"
        assert (
            service.correct(owner_id=owner, actor_id=owner, edition_id=view.id, command=command).id
            == corrected.id
        )
        old = service.get(owner_id=owner, edition_id=view.id)
        assert old.historical_revision and old.title != corrected.title
        with pytest.raises(ApplicationError, match="edition_revision_conflict"):
            service.correct(
                owner_id=owner,
                actor_id=owner,
                edition_id=view.id,
                command=command.model_copy(update={"operation_id": uuid4()}),
            )
    with sessions.begin() as session:
        current = load_current_edition_in_transaction(
            session, owner_id=owner, kind="daily", now=edition.window_end + timedelta(hours=2)
        )
        assert current and current.id == corrected.id
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 5


def test_model_timeout_records_one_receipt_and_never_repays(editorial_client: TestClient) -> None:
    owner, edition, message, lease = _admit(editorial_client, kind="weekly")
    provider = ReportClient()
    provider.failure = AiFailureCode.TIMEOUT
    sessions = editorial_client.app.state.session_factory
    with sessions() as ai_session:
        for _ in range(2):
            with pytest.raises(JobExecutionFailure, match="edition_timeout"):
                _executor(editorial_client, edition).execute(
                    message,
                    lease,
                    ai=AiService(
                        ai_session, provider, clock=lambda: edition.window_end + timedelta(hours=2)
                    ),
                )
    assert provider.calls == 1
    with sessions() as session:
        view = EditionService(session, clock=lambda: edition.window_end + timedelta(hours=2)).get(
            owner_id=owner, edition_id=edition.id
        )
        assert view.status == "unknown" and view.ai_call_id and view.content is None
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 6


@pytest.mark.parametrize("kind", ["weekly", "monthly"])
def test_period_model_runs_once_with_all_fixed_candidates_and_replays(
    editorial_client: TestClient, kind: EditionKind
) -> None:
    owner, edition, message, lease = _admit(editorial_client, kind=kind, candidate_count=2)
    sessions = editorial_client.app.state.session_factory
    now = edition.window_end + timedelta(hours=2)
    provider = ReportClient()
    with sessions() as ai_session:
        ai = AiService(ai_session, provider, clock=lambda: now)
        executor = _executor(editorial_client, edition)
        assert executor.execute(message, lease, ai=ai).status == JobStatus.SUCCEEDED
        assert executor.execute(message, lease, ai=ai).status == JobStatus.SUCCEEDED
    assert provider.calls == 1
    with sessions() as session:
        view = EditionService(session, clock=lambda: now).get(owner_id=owner, edition_id=edition.id)
        assert view.valid and view.generator == "model" and view.ai_call_id and view.content
        assert len(view.content.entries) == 2
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 11


@pytest.mark.parametrize("during_call", [False, True])
def test_withdrawal_hides_whole_draft_and_rejects_late_model(
    editorial_client: TestClient, during_call: bool
) -> None:
    owner, edition, message, lease = _admit(
        editorial_client, kind="weekly" if during_call else "daily"
    )
    sessions = editorial_client.app.state.session_factory

    def revoke() -> None:
        with sessions.begin() as session:
            PublicationService(session).save_source_policy_in_transaction(
                owner_id=owner,
                actor_id=owner,
                source_key="x",
                now=edition.window_end + timedelta(hours=2),
                command=SourcePolicyInput(
                    operation_id=uuid4(),
                    expected_revision=1,
                    participation_mode="isolated",
                    license_name="撤回",
                    reason="受控撤回",
                ),
            )

    if during_call:
        provider = ReportClient(revoke)
        with (
            sessions() as ai_session,
            pytest.raises(JobExecutionFailure, match="edition_input_changed"),
        ):
            _executor(editorial_client, edition).execute(
                message,
                lease,
                ai=AiService(
                    ai_session, provider, clock=lambda: edition.window_end + timedelta(hours=2)
                ),
            )
        assert provider.calls == 1
    else:
        _executor(editorial_client, edition).execute(message, lease)
        revoke()
    with sessions() as session:
        view = EditionService(session, clock=lambda: edition.window_end + timedelta(hours=2)).get(
            owner_id=owner, edition_id=edition.id
        )
        assert (
            not view.valid
            and view.title is None
            and view.content is None
            and view.body_markdown is None
        )
        if during_call:
            assert view.ai_call_id
    with sessions.begin() as session:
        assert (
            load_current_edition_in_transaction(
                session,
                owner_id=owner,
                kind=edition.kind,
                now=edition.window_end + timedelta(hours=2),
            )
            is None
        )


def test_template_crash_resumes_without_turning_into_unknown(
    editorial_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import reports.edition_services as edition_module

    owner, edition, message, lease = _admit(editorial_client)
    compose = edition_module.compose_edition

    def interrupt(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt("controlled process interruption")

    monkeypatch.setattr(edition_module, "compose_edition", interrupt)
    with pytest.raises(KeyboardInterrupt):
        _executor(editorial_client, edition).execute(message, lease)
    sessions = editorial_client.app.state.session_factory
    with sessions() as session:
        view = EditionService(session, clock=lambda: edition.window_end + timedelta(hours=2)).get(
            owner_id=owner, edition_id=edition.id
        )
        assert view.status == "running" and view.generator == "template"
    monkeypatch.setattr(edition_module, "compose_edition", compose)
    assert (
        _executor(editorial_client, edition).execute(message, lease).status == JobStatus.SUCCEEDED
    )
    with sessions() as session:
        view = EditionService(session, clock=lambda: edition.window_end + timedelta(hours=2)).get(
            owner_id=owner, edition_id=edition.id
        )
        assert view.valid and view.status == "complete"
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 5


def test_empty_edition_gaps_advance_durably_and_bound_each_round(
    editorial_client: TestClient,
) -> None:
    owner, edition, _, _ = _admit(editorial_client)
    sessions = editorial_client.app.state.session_factory
    now = edition.window_end + timedelta(hours=12)
    first = (
        (edition.window_start - timedelta(days=400))
        .astimezone(ZoneInfo("Asia/Shanghai"))
        .date()
        .isoformat()
    )
    with sessions.begin() as session:
        assert EditionService(session, clock=lambda: now).enqueue_due_in_transaction(now=now) >= 0
        session.execute(
            text(
                "UPDATE report_edition_schedules SET first_period_key=:first,scan_after_key=NULL "
                "WHERE owner_id=:owner AND kind='daily'"
            ),
            {"first": first, "owner": owner},
        )
    progress = []
    for _ in range(2):
        with sessions.begin() as session:
            assert (
                EditionService(session, clock=lambda: now).enqueue_due_in_transaction(now=now) == 0
            )
            progress.append(
                session.execute(
                    text(
                        "SELECT scan_after_key FROM report_edition_schedules "
                        "WHERE owner_id=:owner AND kind='daily'"
                    ),
                    {"owner": owner},
                ).scalar_one()
            )
    assert progress[0] is not None and progress[1] > progress[0]
    from datetime import date

    assert 1 <= (date.fromisoformat(progress[0]) - date.fromisoformat(first)).days <= 100
    assert 1 <= (date.fromisoformat(progress[1]) - date.fromisoformat(progress[0])).days <= 100
    with sessions() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM report_editions WHERE kind='daily'")
            ).scalar_one()
            == 1
        )


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
def test_model_off_rules_publish_all_kinds_and_replays_preserve_issue(
    editorial_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    kind: EditionKind,
) -> None:
    from tests.integration import test_editorial_execution as editorial_fixture

    # Simulate a different upstream fixture having changed its module's clock.
    monkeypatch.setattr(editorial_fixture, "NOW", NOW - timedelta(days=400))
    owner, edition, message, lease = _admit(editorial_client, kind=kind)
    executor = _executor(editorial_client, edition)
    assert executor.execute(message, lease).status == JobStatus.SUCCEEDED
    sessions = editorial_client.app.state.session_factory
    with sessions() as session:
        service = EditionService(session, clock=lambda: edition.window_end + timedelta(hours=2))
        view = service.get(owner_id=owner, edition_id=edition.id)
        assert view.valid and view.content and view.content.sections and view.body_markdown
        assert view.generator == "template" and view.ai_call_id is None
        operation = session.execute(
            text("SELECT operation_id FROM report_editions WHERE id=:id"), {"id": edition.id}
        ).scalar_one()
        replay = service.request(
            owner_id=owner,
            actor_id=owner,
            command=EditionRequestInput(
                operation_id=operation,
                kind=kind,
                key=edition.key,
                expected_revision=0,
                reason="测试完整自然日" if kind == "daily" else "汇编有效日报",
            ),
        )
        assert replay.id == view.id and replay.content == view.content
        with pytest.raises(ApplicationError, match="edition_revision_conflict"):
            service.request(
                owner_id=owner,
                actor_id=owner,
                command=EditionRequestInput(
                    operation_id=uuid4(),
                    kind=kind,
                    key=edition.key,
                    expected_revision=0,
                    reason="已出刊的窗口不能重新创建",
                ),
            )
        snapshot = session.execute(
            text("SELECT input_snapshot FROM report_editions WHERE id=:id"), {"id": edition.id}
        ).scalar_one()
        assert snapshot[0]["_edition"]["rule_version"] == "edition-rules-v2"
        if kind != "daily":
            assert len(snapshot[0]["_daily_issues"]) == 1
        assert session.execute(text("SELECT count(*) FROM ai_calls")).scalar_one() == 5


def test_daily_never_calls_model_even_when_injected_and_completed_old_versions_replay(
    editorial_client: TestClient,
) -> None:
    owner, edition, message, lease = _admit(editorial_client)
    sessions = editorial_client.app.state.session_factory
    provider = ReportClient()
    with sessions() as ai_session:
        assert (
            _executor(editorial_client, edition)
            .execute(
                message,
                lease,
                ai=AiService(
                    ai_session,
                    provider,
                    clock=lambda: edition.window_end + timedelta(hours=2),
                ),
            )
            .status
            == JobStatus.SUCCEEDED
        )
    assert provider.calls == 0
    with sessions.begin() as session:
        session.execute(
            text("UPDATE report_editions SET prompt_version='legacy-v1' WHERE id=:id"),
            {"id": edition.id},
        )
    assert (
        _executor(editorial_client, edition).execute(message, lease).status == JobStatus.SUCCEEDED
    )
    with sessions() as session:
        view = EditionService(session, clock=lambda: edition.window_end + timedelta(hours=2)).get(
            owner_id=owner,
            edition_id=edition.id,
        )
        assert view.valid and view.generator == "template"


def test_period_requires_completed_latest_daily_and_does_not_fall_back_to_candidates(
    editorial_client: TestClient,
) -> None:
    owner, edition, _, _ = _admit(editorial_client)
    local = edition.window_start.astimezone(ZoneInfo("Asia/Shanghai"))
    year, week, _ = local.isocalendar()
    key = f"{year:04}-W{week:02}"
    _, end = period_window("weekly", key)
    with (
        editorial_client.app.state.session_factory() as session,
        pytest.raises(ApplicationError, match="edition_input_unavailable"),
    ):
        EditionService(session, clock=lambda: end + timedelta(hours=2)).request(
            owner_id=owner,
            actor_id=owner,
            command=EditionRequestInput(
                operation_id=uuid4(),
                kind="weekly",
                key=key,
                expected_revision=0,
                reason="未完成日报不能进入汇编",
            ),
        )


def test_period_revalidates_frozen_daily_revision_after_manual_correction(
    editorial_client: TestClient,
) -> None:
    owner, edition, message, lease = _admit(editorial_client, kind="weekly")
    _executor(editorial_client, edition).execute(message, lease)
    sessions = editorial_client.app.state.session_factory
    at = edition.window_end + timedelta(hours=2)
    with sessions() as session:
        daily_id = session.execute(
            text("SELECT id FROM report_editions WHERE owner_id=:owner AND kind='daily'"),
            {"owner": owner},
        ).scalar_one()
        service = EditionService(session, clock=lambda: at)
        daily = service.get(owner_id=owner, edition_id=daily_id)
        assert daily.content
        service.correct(
            owner_id=owner,
            actor_id=owner,
            edition_id=daily_id,
            command=EditionCorrectionInput(
                operation_id=uuid4(),
                expected_revision=1,
                title="核验后的日报标题",
                lead="核验后的日报导语。",
                highlights=[],
                themes=[],
                reason="修订汇编来源",
            ),
        )
        current = service.get(owner_id=owner, edition_id=edition.id)
        assert current.status == "stale" and not current.valid and current.content is None


@pytest.mark.parametrize("seconds", [-1, 0, 1])
def test_confirmation_boundary_assigns_each_selected_report_to_one_daily(
    editorial_client: TestClient,
    seconds: int,
) -> None:
    owner, run, message, lease = _run(editorial_client, now=NOW)
    _budget(editorial_client, owner, now=NOW)
    _execute(editorial_client, owner, message, lease, ControlledClient(), now=NOW)
    key = NOW.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    _, end = period_window("daily", key)
    confirmation = end + timedelta(seconds=seconds)
    sessions = editorial_client.app.state.session_factory
    with sessions.begin() as session:
        publication = PublicationService(session)
        publication.save_source_policy_in_transaction(
            owner_id=owner,
            actor_id=owner,
            source_key="x",
            now=NOW,
            command=SourcePolicyInput(
                operation_id=uuid4(),
                expected_revision=0,
                participation_mode="editorial",
                license_name="受控许可",
                release_delay_seconds=0,
                reason="确认边界",
            ),
        )
        publication.publish_in_transaction(
            owner_id=owner, content_id=run.content_id, now=confirmation
        )
    following_key = end.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    readable_key, empty_key = (key, following_key) if seconds < 0 else (following_key, key)
    at = end + timedelta(days=1, hours=2)
    with sessions() as session:
        service = EditionService(session, clock=lambda: at)
        with pytest.raises(ApplicationError, match="edition_input_unavailable"):
            service.request(
                owner_id=owner,
                actor_id=owner,
                command=EditionRequestInput(
                    operation_id=uuid4(),
                    kind="daily",
                    key=empty_key,
                    expected_revision=0,
                    reason="该条不属于这一期",
                ),
            )
        edition = service.request(
            owner_id=owner,
            actor_id=owner,
            command=EditionRequestInput(
                operation_id=uuid4(),
                kind="daily",
                key=readable_key,
                expected_revision=0,
                reason="确认时间归期",
            ),
        )
        snapshot = session.execute(
            text("SELECT input_snapshot FROM report_editions WHERE id=:id"), {"id": edition.id}
        ).scalar_one()
        assert [row["content_id"] for row in snapshot] == [str(run.content_id)]
