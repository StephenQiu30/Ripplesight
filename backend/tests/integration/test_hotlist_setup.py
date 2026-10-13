"""Transport setup cannot manufacture or replace platform access decisions."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, text
from tests.integration.test_hotlist_persistence import runtime as runtime
from tests.integration.test_publication_hotlists import grant

from connections.presets import SOURCE_PRESETS
from connections.services import SourcePresetService
from core.errors import ApplicationError
from evidence.schemas import DataClass
from evidence.services import SourceAccessPolicyService, SourceAccessUnavailableError
from sources.adapters.rsshub_hotlist import RsshubHotlistAdapter
from sources.contracts import SourceCapability


def decisions(runtime, owner):
    tables = [
        "source_access_policies",
        "evidence_retention_policies",
        "resource_component_policies",
        "resource_budget_policies",
        "publication_source_policies",
        "source_connections",
        "source_connection_versions",
    ]
    with runtime.engine.connect() as connection:
        return {
            name: [
                dict(row)
                for row in connection.execute(
                    text(f"SELECT * FROM {name} WHERE owner_id=:owner ORDER BY 1"), {"owner": owner}
                ).mappings()
            ]
            for name in tables
        }


def test_first_setup_is_pending_without_retention_component_or_budget_and_no_http(runtime):
    owner = uuid4()
    with runtime.sessions.begin() as session:
        view = SourcePresetService(session, clock=lambda: runtime.due_at).apply_in_transaction(
            owner_id=owner, preset=SOURCE_PRESETS["hotlist_weibo"]
        )
    state = decisions(runtime, owner)
    (row,) = state["source_access_policies"]
    assert (row["status"], row["enabled"], row["reviewed_at"], row["review_expires_at"]) == (
        "pending",
        False,
        None,
        None,
    )
    assert row["access_basis"] is None and row["terms_reference"] is None
    for name in [
        "evidence_retention_policies",
        "resource_component_policies",
        "resource_budget_policies",
        "publication_source_policies",
    ]:
        assert state[name] == []
    requests = []

    def before_request(_attempt):
        with runtime.sessions.begin() as session:
            try:
                SourceAccessPolicyService(
                    session, clock=lambda: runtime.due_at
                ).require_admission_ready_in_transaction(
                    owner_id=owner,
                    source_key="hotlist_weibo",
                    capability=SourceCapability.HOTLIST,
                    data_class=DataClass.STRUCTURED,
                )
            except SourceAccessUnavailableError:
                return False
        raise AssertionError("unreviewed source admitted")

    def fetch(request):
        requests.append(request)
        raise AssertionError("unreviewed source reached HTTP transport")

    adapter = RsshubHotlistAdapter(
        source_key="hotlist_weibo",
        feed_url="http://127.0.0.1:1200/weibo/search/hot",
        allowed_hosts=frozenset({"127.0.0.1"}),
        before_request=before_request,
        transport=httpx.MockTransport(fetch),
    )
    page = adapter.fetch_hotlist()
    assert page.request_count == 0 and requests == []
    writes = []

    def trace(_c, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(None, 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(statement)

    event.listen(runtime.engine, "before_cursor_execute", trace)
    try:
        with runtime.sessions.begin() as session:
            repeated = SourcePresetService(
                session, clock=lambda: runtime.due_at
            ).apply_in_transaction(owner_id=owner, preset=SOURCE_PRESETS["hotlist_weibo"])
    finally:
        event.remove(runtime.engine, "before_cursor_execute", trace)
    assert repeated == view and writes == [] and decisions(runtime, owner) == state


@pytest.mark.parametrize(
    "status,enabled",
    [("pending", False), ("blocked", False), ("approved", False), ("approved", True)],
)
def test_reapply_preserves_review_retention_component_budget_and_public_grant(
    runtime, status, enabled
):
    now = runtime.due_at + timedelta(minutes=2)
    grant(runtime, now)
    with runtime.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE source_access_policies SET status=:status,enabled=:enabled,"
                "review_expires_at=:expiry WHERE owner_id=:owner"
            ),
            {
                "status": status,
                "enabled": enabled,
                "expiry": runtime.due_at + timedelta(seconds=1),
                "owner": runtime.owner_id,
            },
        )
        connection.execute(
            text(
                "UPDATE evidence_retention_policies SET requested_days=7,source_max_days=7,"
                "effective_days=7 WHERE owner_id=:owner"
            ),
            {"owner": runtime.owner_id},
        )
        connection.execute(
            text(
                "UPDATE resource_component_policies SET enabled_for_core=false "
                "WHERE owner_id=:owner"
            ),
            {"owner": runtime.owner_id},
        )
        connection.execute(
            text(
                "UPDATE resource_budget_policies SET enabled=false,limit_units=7 "
                "WHERE owner_id=:owner"
            ),
            {"owner": runtime.owner_id},
        )
    before = decisions(runtime, runtime.owner_id)
    with runtime.sessions.begin() as session:
        SourcePresetService(session, clock=lambda: now).apply_in_transaction(
            owner_id=runtime.owner_id, preset=SOURCE_PRESETS["hotlist_weibo"]
        )
    assert decisions(runtime, runtime.owner_id) == before


def test_changed_transport_conflicts_without_overwriting_decisions(runtime):
    before = decisions(runtime, runtime.owner_id)
    preset = SOURCE_PRESETS["hotlist_weibo"]
    changed = replace(
        preset,
        execution_policy=preset.execution_policy.model_copy(update={"min_interval_seconds": 3600}),
    )
    with pytest.raises(ApplicationError) as captured, runtime.sessions.begin() as session:
        SourcePresetService(session, clock=lambda: runtime.due_at).apply_in_transaction(
            owner_id=runtime.owner_id, preset=changed
        )
    assert captured.value.code == "connection_version_conflict"
    assert decisions(runtime, runtime.owner_id) == before


def test_disabled_transport_is_not_restored(runtime):
    with runtime.engine.begin() as connection:
        connection.execute(
            text("UPDATE source_connections SET status='disabled' WHERE owner_id=:owner"),
            {"owner": runtime.owner_id},
        )
    before = decisions(runtime, runtime.owner_id)
    with pytest.raises(ApplicationError) as captured, runtime.sessions.begin() as session:
        SourcePresetService(session, clock=lambda: runtime.due_at).apply_in_transaction(
            owner_id=runtime.owner_id, preset=SOURCE_PRESETS["hotlist_weibo"]
        )
    assert captured.value.code == "connection_disabled"
    assert decisions(runtime, runtime.owner_id) == before


def test_concurrent_first_setups_share_one_connection_and_pending_policy(runtime):
    owner = uuid4()

    def setup(_):
        with runtime.sessions.begin() as session:
            return SourcePresetService(session, clock=lambda: runtime.due_at).apply_in_transaction(
                owner_id=owner, preset=SOURCE_PRESETS["hotlist_weibo"]
            )

    with ThreadPoolExecutor(max_workers=4) as executor:
        views = list(executor.map(setup, range(4)))
    assert all(view == views[0] for view in views)
    state = decisions(runtime, owner)
    assert (
        len(state["source_connections"])
        == len(state["source_connection_versions"])
        == len(state["source_access_policies"])
        == 1
    )
    assert state["source_access_policies"][0]["policy_version"] == 1


def test_pending_initialization_cannot_replace_existing_review(runtime):
    before = decisions(runtime, runtime.owner_id)
    with runtime.sessions.begin() as session:
        SourceAccessPolicyService(
            session, clock=lambda: runtime.due_at
        ).initialize_pending_in_transaction(
            owner_id=runtime.owner_id,
            source_key="hotlist_weibo",
            capability=SourceCapability.HOTLIST,
            processing_purpose="Proposed new scope",
            field_purposes={"title": "Proposed field"},
        )
    assert decisions(runtime, runtime.owner_id) == before


def test_changed_endpoint_conflicts_without_overwriting_decisions(runtime):
    before = decisions(runtime, runtime.owner_id)
    changed = replace(
        SOURCE_PRESETS["hotlist_weibo"],
        config={
            "feed_url": "http://localhost:1200/weibo/search/hot",
            "allowed_hosts": ("localhost",),
        },
    )
    with pytest.raises(ApplicationError) as captured, runtime.sessions.begin() as session:
        SourcePresetService(session, clock=lambda: runtime.due_at).apply_in_transaction(
            owner_id=runtime.owner_id, preset=changed
        )
    assert captured.value.code == "connection_version_conflict"
    assert decisions(runtime, runtime.owner_id) == before


def test_first_transport_setup_keeps_preexisting_approved_source(runtime):
    from evidence.schemas import AccessBasis, AccessPolicyStatus, SourceAccessPolicyInput

    owner = uuid4()
    preset = SOURCE_PRESETS["hotlist_weibo"]
    with runtime.sessions.begin() as session:
        SourceAccessPolicyService(session, clock=lambda: runtime.due_at).save_in_transaction(
            owner_id=owner,
            command=SourceAccessPolicyInput(
                source_key=preset.source_key,
                capability=SourceCapability.HOTLIST,
                status=AccessPolicyStatus.APPROVED,
                enabled=True,
                access_basis=AccessBasis.WRITTEN_PERMISSION,
                terms_reference="https://example.com/explicit-owner-approval",
                processing_purpose="Controlled source review before transport setup",
                component_name=preset.component_name,
                component_version=preset.component_version,
                component_license=preset.component_license,
                field_purposes={"title": "Controlled scope"},
                reviewed_at=runtime.due_at - timedelta(days=1),
                review_expires_at=runtime.due_at + timedelta(days=1),
            ),
        )
    before = decisions(runtime, owner)["source_access_policies"]
    with runtime.sessions.begin() as session:
        SourcePresetService(session, clock=lambda: runtime.due_at).apply_in_transaction(
            owner_id=owner, preset=preset
        )
    after = decisions(runtime, owner)
    assert after["source_access_policies"] == before
    assert after["evidence_retention_policies"] == []
    assert after["resource_component_policies"] == [] and after["resource_budget_policies"] == []
