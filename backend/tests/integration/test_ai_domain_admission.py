"""Races at the final provider boundary use separate real PostgreSQL transactions."""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration import test_editorial_execution as editorial_fixture
from tests.integration import test_report_editions as edition_fixture
from tests.integration.test_ai_calls import _enable_ai_budget
from tests.integration.test_codex_execution import _runtime_setup
from tests.integration.test_codex_resets import Client, post
from tests.integration.test_translation_recovery import LongTranslationClient
from tests.integration.test_translation_recovery import _admit as admit_translation

from ai.services import AiService
from analysis.editorial_services import EditorialExecutor
from analysis.translation_services import ContentTranslationExecutor
from jobs.execution import JobExecutionFailure
from monitors.codex_services import CodexResetService
from reports.edition_services import EditionExecutor


@pytest.fixture
def editorial_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    for client in editorial_fixture.editorial_client.__wrapped__():
        monkeypatch.setattr(edition_fixture, "NOW", editorial_fixture.NOW)
        yield client


def at_final_admission(monkeypatch: pytest.MonkeyPatch, purpose: str, change: Callable[[], None]):
    original = AiService._reserve
    triggered: list[str] = []

    def reserve(self: AiService, **kwargs: Any):
        if kwargs["purpose"] == purpose and not triggered:
            triggered.append(purpose)
            change()
        return original(self, **kwargs)

    monkeypatch.setattr(AiService, "_reserve", reserve)
    return triggered


def counts(sessions):
    with sessions() as session:
        return tuple(
            session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in ("ai_calls", "resource_budget_reservations", "resource_usage_attempts")
        )


@pytest.mark.parametrize("change", ["permission", "manual"])
def test_translation_final_admission_rechecks_each_frozen_input_before_spending(
    editorial_client, monkeypatch, change
):
    owner, _run, message, lease = admit_translation(editorial_client, 3)
    sessions = editorial_client.app.state.session_factory
    before = counts(sessions)

    def revoke():
        with sessions.begin() as session:
            if change == "permission":
                session.execute(
                    text(
                        "UPDATE publication_source_policies SET configuration="
                        "jsonb_set(configuration,'{site_fulltext}','false') "
                        "WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )
            else:
                session.execute(
                    text(
                        "UPDATE editorial_runs SET manual_version=manual_version+1 "
                        "WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )
                session.execute(
                    text(
                        "UPDATE editorial_content_states SET manual_version=manual_version+1 "
                        "WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )

    triggered = at_final_admission(monkeypatch, "editorial.translation", revoke)
    provider = LongTranslationClient()
    with (
        sessions() as session,
        pytest.raises(JobExecutionFailure, match="translation_material_changed"),
    ):
        ContentTranslationExecutor(
            sessions, editorial_client.app.state.settings, clock=lambda: editorial_fixture.NOW
        ).execute(
            message, lease, ai=AiService(session, provider, clock=lambda: editorial_fixture.NOW)
        )
    assert triggered and provider.calls == 0 and counts(sessions) == before


@pytest.mark.parametrize("change", ["permission", "manual"])
def test_edition_final_admission_rechecks_all_fixed_candidates_before_spending(
    editorial_client, monkeypatch, change
):
    owner, edition, message, lease = edition_fixture._admit(editorial_client)
    sessions = editorial_client.app.state.session_factory
    now = edition.window_end + timedelta(hours=2)
    before = counts(sessions)

    def revoke():
        with sessions.begin() as session:
            if change == "permission":
                session.execute(
                    text(
                        "UPDATE publication_source_policies SET configuration="
                        "jsonb_set(configuration,'{participation_mode}','\"isolated\"') "
                        "WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )
            else:
                session.execute(
                    text(
                        "UPDATE editorial_runs SET manual_version=manual_version+1 "
                        "WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )
                session.execute(
                    text(
                        "UPDATE editorial_content_states SET manual_version=manual_version+1 "
                        "WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )

    triggered = at_final_admission(monkeypatch, "report.edition.daily", revoke)
    provider = edition_fixture.ReportClient()
    with sessions() as session, pytest.raises(JobExecutionFailure, match="edition_input_withdrawn"):
        EditionExecutor(sessions, editorial_client.app.state.settings, clock=lambda: now).execute(
            message, lease, ai=AiService(session, provider, clock=lambda: now)
        )
    assert triggered and provider.calls == 0 and counts(sessions) == before


@pytest.mark.parametrize("change", ["permission", "source", "manual"])
def test_editorial_final_admission_rechecks_captured_manual_and_current_source_permission(
    editorial_client, monkeypatch, change
):
    owner, _run, message, lease = editorial_fixture._run(editorial_client)
    editorial_fixture._budget(editorial_client, owner)
    sessions = editorial_client.app.state.session_factory
    before = counts(sessions)

    def revoke():
        with sessions.begin() as session:
            if change == "permission":
                session.execute(
                    text(
                        "UPDATE source_access_policies SET field_purposes="
                        "field_purposes-'body' WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )
            elif change == "source":
                session.execute(
                    text("UPDATE editorial_sources SET revision=revision+1 WHERE owner_id=:owner"),
                    {"owner": owner},
                )
            else:
                session.execute(
                    text(
                        "UPDATE editorial_runs SET manual_version=manual_version+1 "
                        "WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )
                session.execute(
                    text(
                        "UPDATE editorial_content_states SET manual_version=manual_version+1 "
                        "WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )

    triggered = at_final_admission(monkeypatch, "editorial.prefilter", revoke)
    provider = editorial_fixture.ControlledClient()
    with sessions() as session, pytest.raises(JobExecutionFailure, match="editorial_"):
        EditorialExecutor(
            sessions, editorial_client.app.state.settings, clock=lambda: editorial_fixture.NOW
        ).execute(
            message, lease, ai=AiService(session, provider, clock=lambda: editorial_fixture.NOW)
        )
    assert triggered and not provider.calls and counts(sessions) == before


@pytest.mark.parametrize("change", ["permission", "configuration", "review"])
def test_codex_final_recognition_admission_rechecks_official_permission_and_fixed_context(
    editorial_client, monkeypatch, change
):
    engine = editorial_client.app.state.session_factory.kw["bind"]
    sessions, owner, monitor, _message, _lease, now = _runtime_setup(engine)
    _enable_ai_budget(engine, owner)
    with sessions.begin() as session:
        session.execute(
            text("UPDATE resource_budget_policies SET window_anchor_at=:now WHERE owner_id=:owner"),
            {"owner": owner, "now": now},
        )
    source = post("991", "Will reset at 6pm").model_copy(update={"published_at": now})
    with sessions() as session:
        service = CodexResetService(session, clock=lambda: now)
        service.store_posts(
            owner_id=owner,
            monitor_id=monitor.id,
            posts=(source,),
            expected_configuration_version=monitor.configuration_version,
        )
    before = counts(sessions)

    def revoke():
        with sessions.begin() as session:
            if change == "permission":
                session.execute(
                    text(
                        "UPDATE source_access_policies SET field_purposes="
                        "field_purposes-'body' WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )
            elif change == "configuration":
                session.execute(
                    text("UPDATE codex_reset_monitors SET enabled=false WHERE owner_id=:owner"),
                    {"owner": owner},
                )
            else:
                session.execute(
                    text(
                        "UPDATE codex_reset_posts SET review_version=review_version+1 "
                        "WHERE owner_id=:owner"
                    ),
                    {"owner": owner},
                )

    triggered = at_final_admission(monkeypatch, "monitor.codex_reset.recognize", revoke)
    provider = Client()
    with sessions() as session:
        result = CodexResetService(
            session, ai=AiService(session, provider, clock=lambda: now), clock=lambda: now
        ).process_pending(owner_id=owner, monitor_id=monitor.id)
    assert triggered and result["failed"] == 1 and result["processed"] == 0
    assert not provider.calls and counts(sessions) == before


def test_codex_permission_withdrawn_during_call_preserves_receipt_without_event_or_paid_retry(
    editorial_client,
):
    engine = editorial_client.app.state.session_factory.kw["bind"]
    sessions, owner, monitor, _message, _lease, now = _runtime_setup(engine)
    _enable_ai_budget(engine, owner)
    with sessions.begin() as session:
        session.execute(
            text("UPDATE resource_budget_policies SET window_anchor_at=:now WHERE owner_id=:owner"),
            {"owner": owner, "now": now},
        )
    source = post("993", "Will reset at 6pm").model_copy(update={"published_at": now})
    with sessions() as session:
        CodexResetService(session, clock=lambda: now).store_posts(
            owner_id=owner,
            monitor_id=monitor.id,
            posts=(source,),
            expected_configuration_version=monitor.configuration_version,
        )

    class WithdrawingClient(Client):
        def complete(self, **kwargs):
            with sessions.begin() as session:
                session.execute(
                    text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
                    {"owner": owner},
                )
            return super().complete(**kwargs)

    provider = WithdrawingClient()
    with sessions() as session:
        result = CodexResetService(
            session, ai=AiService(session, provider, clock=lambda: now), clock=lambda: now
        ).process_pending(owner_id=owner, monitor_id=monitor.id)
    assert len(provider.calls) == 1 and result["processed"] == 0
    with sessions.begin() as session:
        assert (
            session.execute(
                text("SELECT count(*) FROM codex_reset_events WHERE owner_id=:owner"),
                {"owner": owner},
            ).scalar_one()
            == 0
        )
        receipt = session.execute(
            text(
                "SELECT r.status,a.status FROM codex_reset_recognitions r "
                "JOIN ai_calls a ON a.id=r.ai_call_id WHERE r.owner_id=:owner"
            ),
            {"owner": owner},
        ).one()
        assert tuple(receipt) == ("stale", "succeeded")
        session.execute(
            text("UPDATE source_access_policies SET enabled=true WHERE owner_id=:owner"),
            {"owner": owner},
        )
    before = counts(sessions)
    with sessions() as session:
        assert (
            CodexResetService(
                session, ai=AiService(session, provider, clock=lambda: now), clock=lambda: now
            ).process_pending(owner_id=owner, monitor_id=monitor.id)["processed"]
            == 0
        )
    assert len(provider.calls) == 1 and counts(sessions) == before


@pytest.fixture
def analysis_case():
    from tests.integration.test_analysis_pipeline import analysis_case as fixture

    yield from fixture.__wrapped__()


@pytest.mark.parametrize("case_kind", ["expired", "during", "none"])
def test_classic_annotation_rechecks_frozen_comment_at_final_admission(
    analysis_case, monkeypatch, case_kind
):
    from tests.integration.test_analysis_pipeline import _make_unreadable, _scan

    from analysis import services as analysis_module
    from analysis.services import AnalysisAnnotateExecutor
    from core.config import Settings
    from jobs.execution import JobExecutionService
    from jobs.schemas import JobAcceptedMessage

    case = analysis_case
    (job_id,) = _scan(case)
    with case.sessions() as session:
        outbox = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": job_id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {
                **outbox.payload,
                "message_id": outbox.id,
                "event_type": outbox.event_type,
                "schema_version": 2,
            }
        )
        session.rollback()
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: case.now).acquire(
            job_id=job_id, worker_id="controlled-final-annotation"
        )
    _enable_ai_budget(case.sessions.kw["bind"], case.owner_id)
    with case.sessions.begin() as session:
        session.execute(
            text("UPDATE resource_budget_policies SET window_anchor_at=:now WHERE owner_id=:owner"),
            {"now": case.now, "owner": case.owner_id},
        )
    before = counts(case.sessions)
    provider = CountingClassicClient()
    if case_kind == "during":
        provider.callback = lambda: _make_unreadable(case, case.comment_id, "expired")
    provider.output = {
        "items": [
            {
                "content_version_id": str(case.version_id),
                "relevant": True,
                "relevance_reason": "Controlled source",
                "sentiment": "neutral",
                "summary": "Controlled source",
                "viewpoints": [],
            }
        ]
    }
    monkeypatch.setattr(analysis_module, "create_ai_client", lambda settings: provider)
    from ai import services as ai_module

    def frozen_client(settings, model):
        provider.frozen_model = model
        provider.provider, provider.model = model.provider, model.model
        return provider

    monkeypatch.setattr(ai_module, "create_ai_client_for_frozen_model", frozen_client)
    triggered = at_final_admission(
        monkeypatch,
        "analysis.annotate",
        (lambda: _make_unreadable(case, case.comment_id, "expired"))
        if case_kind == "expired"
        else lambda: None,
    )
    executor = AnalysisAnnotateExecutor(
        case.sessions,
        Settings(
            _env_file=None,
            database_url=case.sessions.kw["bind"].url.render_as_string(False),
            ai_enabled=True,
        ),
        clock=lambda: case.now,
    )
    if case_kind in {"expired", "during"}:
        with pytest.raises(JobExecutionFailure, match="analysis_"):
            executor.execute(message, lease)
        if case_kind == "expired":
            assert not provider.calls and counts(case.sessions) == before
        else:
            assert provider.calls == 1 and counts(case.sessions)[0] == before[0] + 1
            with case.sessions() as session:
                assert (
                    session.execute(
                        text("SELECT count(*) FROM content_annotations WHERE owner_id=:owner"),
                        {"owner": case.owner_id},
                    ).scalar_one()
                    == 0
                )
    else:
        executor.execute(message, lease)
        assert provider.calls == 1 and counts(case.sessions)[0] == before[0] + 1, (
            triggered,
            counts(case.sessions),
            before,
        )
    assert triggered


@pytest.mark.parametrize("case", ["source", "during", "none", "failed-during"])
def test_classic_daily_report_rechecks_all_source_input_at_final_admission(
    editorial_client, monkeypatch, case
):
    from uuid import uuid4

    from tests.integration.test_content_search import _seed_posts

    from jobs.execution import JobExecutionService
    from jobs.schemas import JobAcceptanceInput, JobAcceptedMessage, JobObservationContext
    from jobs.services import JobService
    from reports import services as reports_module
    from reports.services import DailyReportExecutor

    owner, topic, posts = _seed_posts(editorial_client, [("OpenAI model", "Original body")])
    sessions = editorial_client.app.state.session_factory
    now = editorial_fixture.NOW
    version = posts[0].latest_observation.content_version.id
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE monitor_topic_versions SET match_any='[\"OpenAI\"]'::jsonb "
                "WHERE topic_id=:topic"
            ),
            {"topic": topic},
        )
        call = uuid4()
        session.execute(
            text(
                "INSERT INTO ai_calls (id,owner_id,purpose,provider,model,prompt_version,"
                "input_fingerprint,status,input_tokens,cached_input_tokens,output_tokens,"
                "reasoning_output_tokens,duration_ms,created_at) VALUES "
                "(:id,:owner,'analysis.annotate','controlled','controlled-editorial',"
                "'analysis.annotate.v1',:hash,'succeeded',0,0,0,0,1,:at)"
            ),
            {"id": call, "owner": owner, "hash": call.bytes * 2, "at": now - timedelta(seconds=1)},
        )
        session.execute(
            text(
                "INSERT INTO content_annotations (id,owner_id,content_id,content_version_id,"
                "topic_id,topic_rule_version,prompt_version,relevant,relevance_reason,"
                "sentiment,summary,ai_call_id,status,"
                "result_state,first_valid_at,created_at,updated_at) VALUES "
                "(:id,:owner,:content,:version,:topic,1,'analysis.annotate.v1',"
                "true,'controlled reason','neutral',"
                "'Original summary',:call,'annotated','valid',:at,:at,:at)"
            ),
            {
                "id": uuid4(),
                "owner": owner,
                "content": posts[0].id,
                "version": version,
                "topic": topic,
                "call": call,
                "at": now - timedelta(seconds=1),
            },
        )
        job = JobService(session, clock=lambda: now).accept_in_transaction(
            owner_id=owner,
            command=JobAcceptanceInput(
                kind="report.daily",
                operation_id=uuid4(),
                observation=JobObservationContext(
                    configuration_ref=f"topic:{topic}", configuration_version=1
                ),
                scope={
                    "topic_id": str(topic),
                    "window_start": (now - timedelta(days=1)).isoformat(),
                    "window_end": now.isoformat(),
                },
            ),
        )
    with sessions() as session:
        outbox = session.execute(
            text("SELECT id,event_type,payload FROM outbox_messages WHERE aggregate_id=:job"),
            {"job": job.id},
        ).one()
        message = JobAcceptedMessage.model_validate(
            {
                **outbox.payload,
                "message_id": outbox.id,
                "event_type": outbox.event_type,
                "schema_version": 2,
            }
        )
        session.rollback()
        lease = JobExecutionService(session, lease_seconds=30, clock=lambda: now).acquire(
            job_id=job.id, worker_id="controlled-final-daily"
        )
    editorial_fixture._budget(editorial_client, owner)
    before = counts(sessions)
    provider = CountingClassicClient()
    monkeypatch.setattr(reports_module, "create_ai_client", lambda settings: provider)

    def revoke():
        with sessions.begin() as session:
            session.execute(
                text("UPDATE source_access_policies SET enabled=false WHERE owner_id=:owner"),
                {"owner": owner},
            )

    if case in {"during", "failed-during"}:
        provider.callback = revoke
    if case == "failed-during":
        provider.failed = True
    triggered = at_final_admission(
        monkeypatch, "report.daily", revoke if case == "source" else lambda: None
    )
    executor = DailyReportExecutor(
        sessions,
        settings=editorial_client.app.state.settings.model_copy(update={"ai_enabled": True}),
        clock=lambda: now,
    )
    if case == "none":
        executor.execute(message, lease)
    else:
        with pytest.raises(JobExecutionFailure, match="report_input_changed"):
            executor.execute(message, lease)
    assert triggered
    if case == "source":
        assert provider.calls == 0 and counts(sessions) == before
    else:
        assert provider.calls == 1 and counts(sessions)[0] == before[0] + 1
    with sessions() as session:
        assert session.scalar(text("SELECT count(*) FROM reports")) == int(case == "none")


class CountingClassicClient:
    provider = "controlled"
    model = "controlled-editorial"

    def __init__(self):
        self.calls = 0
        self.callback = None
        self.failed = False
        self.output = {"sections": []}

    def complete(self, **kwargs):
        from ai.schemas import AiCompletion, AiTokenUsage

        self.calls += 1
        if self.callback:
            self.callback()
        if self.failed:
            from ai.schemas import AiCallError, AiFailureCode

            raise AiCallError(AiFailureCode.FAILED)
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output=self.output,
            usage=AiTokenUsage(),
            duration_ms=1,
        )

    def close(self):
        pass
