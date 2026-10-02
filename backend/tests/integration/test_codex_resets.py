from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session
from tests.integration.test_ai_calls import _enable_ai_budget

from ai.schemas import AiCallError, AiCompletion, AiFailureCode, AiTokenUsage
from ai.services import AiService
from core.errors import ApplicationError
from monitors.codex_scan import CodexResetScanService
from monitors.codex_schemas import (
    EventPatch,
    MonitorConfiguration,
    Proposition,
    Recognition,
    ResetPostInput,
    ResetScope,
    ReviewInput,
    ScanAuthorization,
    StatedWords,
)
from monitors.codex_services import CodexResetService
from sources.contracts import (
    SourceCapability,
    SourcePage,
    SourcePageState,
    SourcePost,
    SourceStopReason,
)

NOW = datetime(2026, 9, 25, 9, tzinfo=UTC)


@pytest.fixture
def engine() -> Iterator[Engine]:
    url = os.getenv("HOTKEY_TEST_DATABASE_URL")
    if url is None:
        pytest.skip("isolated PostgreSQL required")
    value = create_engine(url)
    try:
        yield value
    finally:
        value.dispose()


def setup(
    session: Session, *, configuration: MonitorConfiguration | None = None
) -> tuple[CodexResetService, UUID, UUID]:
    owner = uuid4()
    configuration = configuration or MonitorConfiguration(
        connection_id=uuid4(), connection_version=1, author_external_id="12345"
    )
    with session.begin():
        session.execute(
            text(
                "INSERT INTO source_connections "
                "(id,owner_id,source_key,status,current_version,created_at,updated_at) "
                "VALUES (:id,:owner,'x','active',1,:now,:now)"
            ),
            dict(id=configuration.connection_id, owner=owner, now=NOW),
        )
        session.execute(
            text(
                "INSERT INTO source_connection_versions "
                "(connection_id,owner_id,version,auth_kind,secret_ref,config,"
                "created_by,created_at) "
                "VALUES (:id,:owner,1,'server_credential','env:CONTROLLED_X_TOKEN',"
                "'{}'::jsonb,:owner,:now)"
            ),
            dict(id=configuration.connection_id, owner=owner, now=NOW),
        )
        policy = uuid4()
        session.execute(
            text(
                "INSERT INTO source_access_policies "
                "(id,owner_id,source_key,capability,status,enabled,access_basis,terms_reference,"
                "component_name,component_version,component_license,processing_purpose,"
                "field_purposes,reviewed_at,policy_version,created_at,updated_at) "
                "VALUES (:id,:owner,'x','search','approved',true,'official_api','https://example.com/terms',"
                "'official-x','controlled','MIT','Controlled announcements',"
                "CAST(:fields AS jsonb),:now,1,:now,:now)"
            ),
            dict(
                id=policy,
                owner=owner,
                now=NOW,
                fields=json.dumps(
                    {k: "Controlled source policy" for k in ("external_id", "body", "text_scope")}
                ),
            ),
        )
        session.execute(
            text(
                "INSERT INTO evidence_retention_policies "
                "(id,owner_id,source_policy_id,source_policy_version,data_class,"
                "requested_days,effective_days,policy_version,created_at,updated_at) "
                "VALUES (:id,:owner,:policy,1,'structured',30,30,1,:now,:now)"
            ),
            dict(id=uuid4(), owner=owner, policy=policy, now=NOW),
        )
    service = CodexResetService(session, clock=lambda: NOW)
    m = service.create_monitor(owner_id=owner, configuration=configuration)
    service.configure(owner_id=owner, monitor_id=m.id, expected_revision=m.revision, enabled=True)
    return service, owner, m.id


def post(external_id: str, message: str, hours: float = 0) -> ResetPostInput:
    return ResetPostInput(
        external_id=external_id,
        text=message,
        published_at=NOW + timedelta(hours=hours),
        url=f"https://x.com/thsottiaux/status/{external_id}",
    )


def apply(
    service: CodexResetService,
    owner: UUID,
    monitor: UUID,
    source: ResetPostInput,
    action: str,
    *,
    kind: str = "direct_reset",
    **extra: Any,
) -> Any:
    m = service.get_monitor(owner_id=owner, monitor_id=monitor)
    service.store_posts(
        owner_id=owner,
        monitor_id=monitor,
        posts=(source,),
        expected_configuration_version=m.configuration_version,
    )
    prepared = service.prepare_next(owner_id=owner, monitor_id=monitor)
    assert prepared is not None
    p = Proposition.model_validate(
        dict(kind=kind, action=action, real=True, kind_explicit=True, excerpt=source.text, **extra)
    )
    return service.apply_recognition(
        prepared=prepared,
        recognition=Recognition(relevant=True, needs_review=False, propositions=(p,)),
    )


def review(version: int, **extra: Any) -> ReviewInput:
    return ReviewInput(
        operation_id=uuid4(),
        expected_revision=version,
        reason="checked source evidence",
        actor="test-operator",
        **extra,
    )


def test_program_state_scope_amend_progress_confirm_and_notification_intents(
    engine: Engine,
) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        first = apply(
            s,
            owner,
            monitor,
            post("100", "Reset landing at 6pm"),
            "announce",
            stated_time=StatedWords(precision="exact", clock="18:00"),
        )
        event = first.event_ids[0]
        assert first.notifications[0].action == "announce"
        progress = apply(
            s, owner, monitor, post("101", "Reset rolling out", 1), "progress", relates_to=event
        )
        assert not progress.notifications
        changed = apply(
            s,
            owner,
            monitor,
            post("102", "Reset for all paid users", 2),
            "amend",
            relates_to=event,
            scope=ResetScope(audience_source="all paid users", audience_zh="所有付费用户"),
        )
        assert changed.notifications[0].action == "amend"
        confirmed = apply(
            s, owner, monitor, post("103", "Reset all propagated", 3), "confirm", relates_to=event
        )
        assert confirmed.notifications[0].action == "confirm"
        snap = s.snapshot(owner_id=owner, monitor_id=monitor)
        e = snap.events[0]
        assert e.status == "confirmed" and e.confirmation_basis == "source_post"
        assert e.estimate is None and e.schedule is not None and len(e.posts) == 4
        assert e.scope.audience_source == "all paid users"
        assert len(s.notification_intents(owner_id=owner, monitor_id=monitor)) == 3
        prepared = s.prepare_next(owner_id=owner, monitor_id=monitor)
        assert prepared is None


def test_count_duplicates_and_kinds_are_independent(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        multiple = apply(s, owner, monitor, post("200", "We'll reset twice"), "announce", count=2)
        assert len(multiple.event_ids) == 2
        apply(
            s,
            owner,
            monitor,
            post("201", "Loading a banked reset", 1),
            "announce",
            kind="reset_credit",
        )
        assert len(s.snapshot(owner_id=owner, monitor_id=monitor).events) == 3
        s.store_posts(
            owner_id=owner,
            monitor_id=monitor,
            posts=(post("200", "We'll reset twice"),),
            expected_configuration_version=1,
        )
        assert s.prepare_next(owner_id=owner, monitor_id=monitor) is None
        with pytest.raises(ApplicationError, match="codex_version_conflict"):
            s.store_posts(
                owner_id=owner,
                monitor_id=monitor,
                posts=(post("200", "Different edited evidence"),),
                expected_configuration_version=1,
            )


def test_fabricated_quote_and_uncertainty_hold_public_changes(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        s.store_posts(
            owner_id=owner,
            monitor_id=monitor,
            posts=(post("300", "We'll reset tomorrow"),),
            expected_configuration_version=1,
        )
        p = s.prepare_next(owner_id=owner, monitor_id=monitor)
        assert p is not None
        result = s.apply_recognition(
            prepared=p,
            recognition=Recognition(
                relevant=True,
                needs_review=False,
                outage="outage",
                propositions=(
                    Proposition(
                        kind="direct_reset",
                        action="confirm",
                        real=True,
                        excerpt="All reset propagated",
                    ),
                ),
            ),
        )
        assert result.status == "held" and not result.event_ids
        snap = s.snapshot(owner_id=owner, monitor_id=monitor)
        assert not snap.events and snap.outage is None and snap.monitor.review_count == 1
        assert not s.verify_if_complete(owner_id=owner, monitor_id=monitor, collected_at=NOW)


def test_old_model_result_cannot_overwrite_manual_or_configuration_epoch(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        event = apply(s, owner, monitor, post("400", "Will reset"), "announce").event_ids[0]
        s.store_posts(
            owner_id=owner,
            monitor_id=monitor,
            posts=(post("401", "Reset all done", 1),),
            expected_configuration_version=1,
        )
        prepared = s.prepare_next(owner_id=owner, monitor_id=monitor)
        assert prepared is not None
        s.update_event(
            owner_id=owner,
            monitor_id=monitor,
            event_id=event,
            patch=EventPatch(withdrawn=True),
            review=review(1),
        )
        result = s.apply_recognition(
            prepared=prepared,
            recognition=Recognition(
                relevant=True,
                needs_review=False,
                propositions=(
                    Proposition(
                        kind="direct_reset",
                        action="confirm",
                        real=True,
                        excerpt="Reset all done",
                        relates_to=event,
                    ),
                ),
            ),
        )
        assert result.status == "stale" and not result.notifications
        assert (
            s.snapshot(owner_id=owner, monitor_id=monitor, include_withdrawn=True)
            .events[0]
            .withdrawn
        )
        assert len(s.list_posts(owner_id=owner, monitor_id=monitor, filter_key="pending")) == 1
        m = s.get_monitor(owner_id=owner, monitor_id=monitor)
        s.configure(owner_id=owner, monitor_id=monitor, expected_revision=m.revision, enabled=False)
        with pytest.raises(ApplicationError, match="codex_monitor_disabled"):
            s.prepare_next(owner_id=owner, monitor_id=monitor)


def test_out_of_order_late_announcement_does_not_duplicate_completed_round(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        done = apply(s, owner, monitor, post("502", "All reset done", 2), "confirm").event_ids[0]
        late = apply(s, owner, monitor, post("500", "Will reset in next hour"), "announce")
        assert late.event_ids == (done,) and not late.notifications
        snap = s.snapshot(owner_id=owner, monitor_id=monitor)
        assert len(snap.events) == 1 and snap.events[0].status == "confirmed"
        assert snap.events[0].created_at == NOW and snap.events[0].confirmed_at == NOW + timedelta(
            hours=2
        )


def test_withdraw_restore_review_idempotency_and_manual_receipt(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        event = apply(s, owner, monitor, post("600", "We'll reset"), "announce").event_ids[0]
        withdrawn = apply(
            s, owner, monitor, post("601", "Reset cancelled", 1), "withdraw", relates_to=event
        )
        assert withdrawn.notifications[0].action == "withdraw"
        assert not s.snapshot(owner_id=owner, monitor_id=monitor).events
        r = review(2)
        restored = s.update_event(
            owner_id=owner,
            monitor_id=monitor,
            event_id=event,
            patch=EventPatch(withdrawn=False),
            review=r,
        )
        assert restored.revision == 3 and not restored.withdrawn
        assert (
            s.update_event(
                owner_id=owner,
                monitor_id=monitor,
                event_id=event,
                patch=EventPatch(withdrawn=False),
                review=r,
            )
            == restored
        )
        with pytest.raises(ApplicationError, match="codex_version_conflict"):
            s.update_event(
                owner_id=owner,
                monitor_id=monitor,
                event_id=event,
                patch=EventPatch(withdrawn=True),
                review=r,
            )
        received = s.review_receipt(
            owner_id=owner,
            monitor_id=monitor,
            event_id=event,
            review=review(3),
            occurred_on=NOW.date(),
        )
        assert received.confirmation_basis == "receipt_review" and received.confirmed_at is None
        official = apply(
            s, owner, monitor, post("602", "All reset done", 2), "confirm", relates_to=event
        )
        assert not official.notifications
        assert (
            s.snapshot(owner_id=owner, monitor_id=monitor).events[0].confirmation_basis
            == "source_post"
        )


def test_paused_model_persists_failure_then_skip_unblocks_order(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        s.store_posts(
            owner_id=owner,
            monitor_id=monitor,
            posts=(post("700", "first"), post("701", "second", 1)),
            expected_configuration_version=1,
        )
        assert s.process_pending(owner_id=owner, monitor_id=monitor) == {
            "processed": 0,
            "failed": 1,
            "notifications_enqueued": 0,
        }
        pending = s.list_posts(owner_id=owner, monitor_id=monitor, filter_key="pending")
        first = next(p for p in pending if p.external_id == "700")
        assert first.failure_count == 1 and first.failure_code == "unavailable"
        s.resolve_post(
            owner_id=owner, monitor_id=monitor, post_id=first.id, action="skip", review=review(1)
        )
        next_post = s.prepare_next(owner_id=owner, monitor_id=monitor)
        assert next_post and next_post.post.external_id == "701"
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM ai_calls")) == 0


def source_post(external_id: str) -> SourcePost:
    return SourcePost(
        source_key="x",
        external_id=external_id,
        author_external_id="12345",
        published_at=NOW,
        text=f"Reset {external_id}",
        text_scope="full",
        like_count=None,
        comment_count=None,
        repost_count=None,
    )


class Source:
    def __init__(self, *, loop: bool = False) -> None:
        self.requests: list[Any] = []
        self.loop = loop

    def fetch_page(self, request: Any) -> SourcePage:
        self.requests.append(request)
        token = request.page_token
        ids, next_token = (
            ("900", "p1")
            if token is None
            else ("800", "p1" if self.loop else "p2")
            if token == "p1"
            else ("750", None)
        )
        return SourcePage(
            source_key="x",
            capability=SourceCapability.SEARCH,
            state=SourcePageState.MORE if next_token else SourcePageState.COMPLETE,
            items=(source_post(ids),),
            next_page_token=next_token,
            watermark=None,
            stop_reason=None if next_token else SourceStopReason.END_OF_RESULTS,
            observed_at=NOW,
        )


def authorized() -> ScanAuthorization:
    return ScanAuthorization(
        connection_enabled=True,
        credentials_confirmed=True,
        owner_authorized=True,
        budget_confirmed=True,
    )


def test_scan_authorization_zero_requests_and_backlog_survives_new_service(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        config = MonitorConfiguration(
            connection_id=uuid4(), connection_version=1, author_external_id="12345", max_pages=1
        )
        s, owner, monitor = setup(session, configuration=config)
        provider = Source()
        scanner = CodexResetScanService(session, source=provider, clock=lambda: NOW)
        blocked = scanner.collect(owner_id=owner, monitor_id=monitor)
        assert blocked.status == "blocked" and not provider.requests
        first = scanner.collect(owner_id=owner, monitor_id=monitor, authorization=authorized())
        assert first.stored == 2 and first.pages == 2 and first.backlog == 1
        assert s.prepare_next(owner_id=owner, monitor_id=monitor) is None
    with Session(engine, expire_on_commit=False) as session:
        restarted = CodexResetScanService(
            session, source=provider, clock=lambda: NOW + timedelta(minutes=5)
        )
        result = restarted.collect(owner_id=owner, monitor_id=monitor, authorization=authorized())
        assert result.stored == 1 and result.backlog == 0
        s = CodexResetService(session, clock=lambda: NOW + timedelta(minutes=5))
        next_post = s.prepare_next(owner_id=owner, monitor_id=monitor)
        assert next_post and next_post.post.external_id == "750"


def test_cursor_loop_is_persistent_attention_gap(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(
            session,
            configuration=MonitorConfiguration(
                connection_id=uuid4(), connection_version=1, author_external_id="12345", max_pages=1
            ),
        )
        result = CodexResetScanService(
            session, source=Source(loop=True), clock=lambda: NOW
        ).collect(owner_id=owner, monitor_id=monitor, authorization=authorized())
        assert result.status == "partial" and result.reason == "cursor_loop" and result.backlog == 1
        snap = s.snapshot(owner_id=owner, monitor_id=monitor)
        assert snap.monitor.held_window_count == 1 and snap.monitor.last_verified_at is None
        assert not s.verify_if_complete(owner_id=owner, monitor_id=monitor, collected_at=NOW)


class Client:
    provider = "controlled"
    model = "controlled-reset"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(
        self, *, prompt: str, output_schema: Mapping[str, Any], instructions: str = ""
    ) -> AiCompletion:
        self.calls.append(prompt)
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            usage=AiTokenUsage(),
            duration_ms=1,
            output=Recognition(
                relevant=True,
                needs_review=False,
                propositions=(
                    Proposition(
                        kind="direct_reset", action="announce", real=True, excerpt="Will reset"
                    ),
                ),
            ).model_dump(mode="json"),
        )

    def close(self) -> None:
        pass


def test_real_ai_service_receipt_and_restart_read_are_persistent(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        s.store_posts(
            owner_id=owner,
            monitor_id=monitor,
            posts=(post("990", "Will reset"),),
            expected_configuration_version=1,
        )
    _enable_ai_budget(engine, owner)
    with Session(engine, expire_on_commit=False) as session:
        service = CodexResetService(
            session, ai=AiService(session, Client(), clock=lambda: NOW), clock=lambda: NOW
        )
        assert service.process_pending(owner_id=owner, monitor_id=monitor) == {
            "processed": 1,
            "failed": 0,
            "notifications_enqueued": 0,
        }
    with engine.connect() as c:
        assert (
            c.scalar(
                text("SELECT count(*) FROM codex_reset_recognitions WHERE ai_call_id IS NOT NULL")
            )
            == 1
        )
        assert (
            c.scalar(
                text(
                    "SELECT count(*) FROM ai_calls WHERE purpose = 'monitor.codex_reset.recognize'"
                )
            )
            == 1
        )
    with Session(engine, expire_on_commit=False) as session:
        snapshot = CodexResetService(session, clock=lambda: NOW).snapshot(
            owner_id=owner, monitor_id=monitor
        )
        assert len(snapshot.calendar) == 1 and snapshot.events[0].status == "announced"


def test_outage_recovery_reset_link_and_visibility_are_source_based(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        for source, kind in (
            (post("1100", "Codex is down"), "outage"),
            (post("1101", "Codex recovered", 1), "recovery"),
        ):
            s.store_posts(
                owner_id=owner,
                monitor_id=monitor,
                posts=(source,),
                expected_configuration_version=1,
            )
            prepared = s.prepare_next(owner_id=owner, monitor_id=monitor)
            assert prepared is not None
            s.apply_recognition(
                prepared=prepared,
                recognition=Recognition.model_validate(
                    dict(relevant=True, needs_review=False, outage=kind, propositions=[])
                ),
            )
        event = apply(s, owner, monitor, post("1102", "Will reset", 2), "announce").event_ids[0]
        snap = s.snapshot(owner_id=owner, monitor_id=monitor, now=NOW + timedelta(hours=2))
        assert snap.outage and snap.outage.recovered_at == NOW + timedelta(hours=1)
        assert snap.outage.reset_event_id == event
        assert (
            s.version_probe(
                owner_id=owner, monitor_id=monitor, now=NOW + timedelta(hours=2)
            ).version
            == snap.version
        )
        assert (
            s.snapshot(owner_id=owner, monitor_id=monitor, now=NOW + timedelta(hours=19)).outage
            is None
        )


def test_review_relink_preserves_audit_and_source_partition(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        one = apply(s, owner, monitor, post("1200", "Will reset"), "announce").event_ids[0]
        two = apply(
            s, owner, monitor, post("1201", "Another reset coming", 1), "announce"
        ).event_ids[0]
        source = next(
            p
            for p in s.list_posts(owner_id=owner, monitor_id=monitor, filter_key="all")
            if p.external_id == "1200"
        )
        r = review(1)
        moved = s.relink_post(
            owner_id=owner,
            monitor_id=monitor,
            post_id=source.id,
            from_event_id=one,
            to_event_id=two,
            target_expected_revision=1,
            review=r,
        )
        assert moved.event_ids == (two,)
        assert (
            s.relink_post(
                owner_id=owner,
                monitor_id=monitor,
                post_id=source.id,
                from_event_id=one,
                to_event_id=two,
                target_expected_revision=1,
                review=r,
            )
            == moved
        )
        with pytest.raises(ApplicationError, match="resource_not_found"):
            s.snapshot(owner_id=uuid4(), monitor_id=monitor)
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM codex_reset_reviews")) == 1


def test_gap_acknowledgement_preserves_unknown_coverage_and_can_process_known_posts(
    engine: Engine,
) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(
            session,
            configuration=MonitorConfiguration(
                connection_id=uuid4(), connection_version=1, author_external_id="12345", max_pages=1
            ),
        )
        CodexResetScanService(session, source=Source(loop=True), clock=lambda: NOW).collect(
            owner_id=owner, monitor_id=monitor, authorization=authorized()
        )
        gap = s.list_gaps(owner_id=owner, monitor_id=monitor)[0]
        acknowledged = s.resolve_gap(
            owner_id=owner,
            monitor_id=monitor,
            gap_id=gap.id,
            action="acknowledge",
            review=review(gap.monitor_revision),
        )
        assert (
            acknowledged.state == "held"
            and acknowledged.failure_code == "operator_acknowledged_gap"
        )
        assert s.prepare_next(owner_id=owner, monitor_id=monitor) is not None
        assert not s.verify_if_complete(owner_id=owner, monitor_id=monitor, collected_at=NOW)
        retry = s.resolve_gap(
            owner_id=owner,
            monitor_id=monitor,
            gap_id=gap.id,
            action="retry",
            review=review(acknowledged.monitor_revision),
        )
        assert retry.state == "pending" and retry.has_resume_token
        assert s.prepare_next(owner_id=owner, monitor_id=monitor) is None


def test_read_paths_never_create_monitors_or_modify_facts_and_clock_changes_version(
    engine: Engine,
) -> None:
    owner = uuid4()
    with Session(engine, expire_on_commit=False) as session:
        reader = CodexResetService(session, clock=lambda: NOW)
        assert reader.get_existing_monitor(owner_id=owner) is None
    with engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM codex_reset_monitors")) == 0
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        apply(
            s,
            owner,
            monitor,
            post("1300", "Reset by 3am"),
            "announce",
            stated_time=StatedWords(precision="deadline", clock="03:00"),
        )
    with engine.connect() as c:
        before = {
            name: c.execute(
                text(f"SELECT array_agg(t::text ORDER BY t::text) FROM {name} t")
            ).scalar()
            for name in (
                "codex_reset_posts",
                "codex_reset_events",
                "codex_reset_recognitions",
                "ai_calls",
                "jobs",
                "outbox_messages",
            )
        }
    with Session(engine, expire_on_commit=False) as session:
        s = CodexResetService(session, clock=lambda: NOW)
        fresh = s.snapshot(owner_id=owner, monitor_id=monitor)
        expired = s.snapshot(owner_id=owner, monitor_id=monitor, now=NOW + timedelta(hours=3))
        likely = s.snapshot(owner_id=owner, monitor_id=monitor, now=NOW + timedelta(hours=9))
        assert (
            fresh.events[0].status
            == expired.events[0].status
            == likely.events[0].status
            == "announced"
        )
        assert len({fresh.version, expired.version, likely.version}) == 3
        assert s.version_probe(owner_id=owner, monitor_id=monitor).version == fresh.version
        assert (
            s.version_probe(
                owner_id=owner, monitor_id=monitor, now=NOW + timedelta(hours=9)
            ).version
            == likely.version
        )
    with engine.connect() as c:
        after = {
            name: c.execute(
                text(f"SELECT array_agg(t::text ORDER BY t::text) FROM {name} t")
            ).scalar()
            for name in before
        }
    assert before == after


def test_manual_review_cannot_claim_official_confirmation_and_clears_review_count(
    engine: Engine,
) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        event = apply(s, owner, monitor, post("1400", "Will reset"), "announce").event_ids[0]
        with pytest.raises(ApplicationError, match="invalid_codex_input"):
            s.update_event(
                owner_id=owner,
                monitor_id=monitor,
                event_id=event,
                patch=EventPatch(status="confirmed", confirmation_basis="source_post"),
                review=review(1),
            )
        s.store_posts(
            owner_id=owner,
            monitor_id=monitor,
            posts=(post("1401", "Maybe reset", 1),),
            expected_configuration_version=1,
        )
        prepared = s.prepare_next(owner_id=owner, monitor_id=monitor)
        assert prepared is not None
        s.apply_recognition(
            prepared=prepared,
            recognition=Recognition(
                relevant=True,
                needs_review=True,
                propositions=(
                    Proposition(
                        kind="direct_reset", action="confirm", real=True, excerpt="Maybe reset"
                    ),
                ),
            ),
        )
        held = s.list_posts(owner_id=owner, monitor_id=monitor, filter_key="review")[0]
        assert held.needs_review and not held.reviewed
        s.resolve_post(
            owner_id=owner, monitor_id=monitor, post_id=held.id, action="reviewed", review=review(1)
        )
        assert s.snapshot(owner_id=owner, monitor_id=monitor).monitor.review_count == 0


class FailedClient(Client):
    def complete(
        self, *, prompt: str, output_schema: Mapping[str, Any], instructions: str = ""
    ) -> AiCompletion:
        raise AiCallError(AiFailureCode.TIMEOUT)


def test_failed_ai_receipt_remains_linked_to_unknown_post_and_stops_order(engine: Engine) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(session)
        s.store_posts(
            owner_id=owner,
            monitor_id=monitor,
            posts=(post("1500", "Will reset"), post("1501", "All reset done", 1)),
            expected_configuration_version=1,
        )
    _enable_ai_budget(engine, owner)
    with Session(engine, expire_on_commit=False) as session:
        s = CodexResetService(
            session, ai=AiService(session, FailedClient(), clock=lambda: NOW), clock=lambda: NOW
        )
        assert s.process_pending(owner_id=owner, monitor_id=monitor) == {
            "processed": 0,
            "failed": 1,
            "notifications_enqueued": 0,
        }
        assert not s.snapshot(owner_id=owner, monitor_id=monitor).events
        assert len(s.list_posts(owner_id=owner, monitor_id=monitor, filter_key="pending")) == 2
    with engine.connect() as c:
        row = c.execute(
            text(
                "SELECT r.status, r.recognition->>'status', a.status, a.failure_code "
                "FROM codex_reset_recognitions r JOIN ai_calls a ON a.id=r.ai_call_id"
            )
        ).one()
        assert tuple(row) == ("unknown", "unknown", "unknown", "timeout")


@pytest.mark.parametrize(
    "missing",
    ["connection_enabled", "credentials_confirmed", "owner_authorized", "budget_confirmed"],
)
def test_every_authorization_gate_is_required_and_zero_request(
    engine: Engine, missing: str
) -> None:
    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(
            session,
            configuration=MonitorConfiguration(
                connection_id=uuid4(), connection_version=1, author_external_id="12345"
            ),
        )
        provider = Source()
        authorization = authorized().model_copy(update={missing: False})
        assert (
            CodexResetScanService(session, source=provider, clock=lambda: NOW)
            .collect(owner_id=owner, monitor_id=monitor, authorization=authorization)
            .status
            == "blocked"
        )
        assert not provider.requests and not s.list_gaps(owner_id=owner, monitor_id=monitor)


def test_context_missing_never_moves_coverage_cursor(engine: Engine) -> None:
    class ReplySource(Source):
        def fetch_page(self, request: Any) -> SourcePage:
            self.requests.append(request)
            return SourcePage(
                source_key="x",
                capability=SourceCapability.SEARCH,
                state=SourcePageState.COMPLETE,
                items=(source_post("1600").model_copy(update={"parent_external_id": "1599"}),),
                next_page_token=None,
                watermark=None,
                stop_reason=SourceStopReason.END_OF_RESULTS,
                observed_at=NOW,
            )

    with Session(engine, expire_on_commit=False) as session:
        s, owner, monitor = setup(
            session,
            configuration=MonitorConfiguration(
                connection_id=uuid4(), connection_version=1, author_external_id="12345"
            ),
        )
        provider = ReplySource()
        result = CodexResetScanService(session, source=provider, clock=lambda: NOW).collect(
            owner_id=owner, monitor_id=monitor, authorization=authorized()
        )
        assert result.status == "partial" and result.reason == "context_unavailable"
        assert not s.list_posts(owner_id=owner, monitor_id=monitor, filter_key="all")
        assert s.list_gaps(owner_id=owner, monitor_id=monitor)[0].state == "held"
    with engine.connect() as c:
        assert c.scalar(text("SELECT since_id FROM codex_reset_monitors")) is None


def test_relink_http_requires_operator_and_both_cas_and_preserves_original_posts(engine):
    from fastapi.testclient import TestClient

    from core.config import Settings
    from main import create_app

    with Session(engine, expire_on_commit=False) as session:
        service, owner, monitor = setup(session)
        source_event = apply(
            service, owner, monitor, post("1901", "Controlled first reset"), "announce"
        ).event_ids[0]
        target_event = apply(
            service, owner, monitor, post("1902", "Controlled second reset", 1), "announce"
        ).event_ids[0]
        source_post = next(
            item
            for item in service.list_posts(owner_id=owner, monitor_id=monitor, filter_key="all")
            if item.external_id == "1901"
        )
    command = {
        "from_event_id": source_event,
        "to_event_id": target_event,
        "target_expected_revision": 1,
        "review": {
            "operation_id": str(uuid4()),
            "expected_revision": 1,
            "reason": "Controlled attribution correction",
            "actor": "operator",
        },
    }
    app = create_app(
        Settings(
            _env_file=None,
            environment="test",
            log_level="WARNING",
            database_url=engine.url.render_as_string(hide_password=False),
            operator_token="controlled-route-token",
        )
    )
    path = f"/api/codex-resets/monitors/{monitor}/posts/{source_post.id}/relink"
    with TestClient(app) as client:
        from tests.conftest import authenticate_test_client

        assert client.post(path, json=command).status_code == 401
        authenticate_test_client(client, owner_id=owner)
        assert client.post(path, json=command).status_code == 401
        token = {"X-HotKey-Operator-Token": "controlled-route-token"}
        assert client.post(path, json=command, headers=token).status_code == 403
        headers = {**token, "X-HotKey-CSRF": client.cookies["hotkey_csrf"]}
        bad_pair = client.post(
            path, json={**command, "target_expected_revision": None}, headers=headers
        )
        assert bad_pair.status_code == 422 and bad_pair.json()["code"] == "validation_error"
        stale = client.post(path, json={**command, "target_expected_revision": 2}, headers=headers)
        assert stale.status_code == 409 and stale.json()["code"] == "codex_version_conflict"
        response = client.post(path, json=command, headers=headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json()["event_ids"] == [target_event]
        assert client.post(path, json=command, headers=headers).json() == response.json()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM codex_reset_posts")) == 2
        assert connection.scalar(text("SELECT count(*) FROM codex_reset_reviews")) == 1
        assert connection.scalar(text("SELECT count(*) FROM ai_calls")) == 0
