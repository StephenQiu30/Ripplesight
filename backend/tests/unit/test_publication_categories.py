"""Public configuration gates current projections and scopes the existing sync protocol."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

import publication.reading as reading
from core.config import Settings
from core.errors import ApplicationError
from publication.cursors import decode_cursor
from publication.reading import PublicationReadingService
from tests.unit.test_publication_groups import member

NOW = datetime(2026, 10, 2, tzinfo=UTC)


def test_category_setting_accepts_six_independent_keys_and_normalizes_json(monkeypatch):
    options = {
        "_env_file": None,
        "database_url": "postgresql+psycopg://localhost/hotkey_test_categories",
        "environment": "test",
    }
    monkeypatch.delenv("HOTKEY_PUBLIC_PUBLICATION_CATEGORIES", raising=False)
    assert Settings(**options).public_publication_categories == ()
    monkeypatch.setenv("HOTKEY_PUBLIC_PUBLICATION_CATEGORIES", '["tip","opinion","tip"]')
    assert Settings(**options).public_publication_categories == ("opinion", "tip")
    monkeypatch.setenv("HOTKEY_PUBLIC_PUBLICATION_CATEGORIES", '["unknown"]')
    with pytest.raises(ValidationError):
        Settings(**options)


@pytest.mark.parametrize(
    "category", ["ai-models", "ai-products", "industry", "paper", "tip", "opinion", None]
)
@pytest.mark.parametrize("configured", [(), ("tip",), ("opinion", "paper")])
def test_live_gate_uses_current_category_without_merging_or_bypassing_permission(
    monkeypatch, category, configured
):
    # The stored category intentionally differs: the current derived projection is authoritative.
    stored = member(at=NOW).projection
    current = stored.model_copy(update={"category": category})
    row = SimpleNamespace(
        content_id=stored.content_id,
        content_version_id=stored.content_version_id,
        source_key=stored.source_key,
        visibility="public",
        data=stored.model_dump(mode="json"),
        override={},
    )
    snapshot = SimpleNamespace(
        observation_id=None,
        run=SimpleNamespace(id=stored.editorial_run_id, manual_version=stored.manual_version),
        material=SimpleNamespace(
            content_version_id=stored.content_version_id, source_key=stored.source_key
        ),
    )
    policy = SimpleNamespace(
        source_key=stored.source_key, configuration={"participation_mode": "editorial"}
    )
    session = SimpleNamespace(in_transaction=lambda: True, scalars=lambda _: [policy])
    monkeypatch.setattr(
        "connections.editorial_icon_services.read_source_icon_urls_in_transaction",
        lambda *a, **k: {},
    )
    monkeypatch.setattr(
        reading,
        "load_editorial_publication_inputs_in_transaction",
        lambda *a, **k: {stored.content_id: snapshot},
    )
    monkeypatch.setattr(
        reading,
        "load_publication_selection_in_transaction",
        lambda *a, **k: SimpleNamespace(groupings={}, gates={}),
    )
    monkeypatch.setattr(reading, "policy_view", lambda _: None)
    monkeypatch.setattr(reading, "derive_projection", lambda *a, **k: current)
    reader = PublicationReadingService(session, public_categories=configured)
    result = reader._live(owner_id=uuid4(), rows=[row], now=NOW)
    assert bool(result) == (not configured or category in configured)
    policy.configuration["participation_mode"] = "isolated"
    assert reader._live(owner_id=uuid4(), rows=[row], now=NOW) == {}


def test_snapshot_and_changes_bind_normalized_categories_but_query_original_ledger(monkeypatch):
    owner, persistent_epoch = uuid4(), uuid4()
    projections = [member(at=NOW).projection for _ in range(2)]
    records = [SimpleNamespace(content_id=p.content_id, sort_at=NOW) for p in projections]
    ledger = [
        SimpleNamespace(content_id=p.content_id, sequence=i + 1, operation="upsert", changed_at=NOW)
        for i, p in enumerate(projections)
    ]
    queries = []

    def scalars(query):
        queries.append(query)
        return ledger if "publication_selected_changes" in str(query) else records

    session = SimpleNamespace(in_transaction=lambda: True, scalars=scalars)
    reader = PublicationReadingService(session, public_categories=("tip", "opinion", "tip"))
    monkeypatch.setattr(
        reader, "effective_sequence_in_transaction", lambda **_: (persistent_epoch, 2)
    )
    monkeypatch.setattr(reader, "_live", lambda **_: {p.content_id: (p, None) for p in projections})
    snapshot = reader.selected_snapshot_in_transaction(owner_id=owner, now=NOW, limit=1)
    assert snapshot.epoch != persistent_epoch and snapshot.next_cursor
    same = PublicationReadingService(session, public_categories=("opinion", "tip"))
    assert same._selected_read_epoch(persistent_epoch) == snapshot.epoch
    changed = PublicationReadingService(session, public_categories=("tip",))
    monkeypatch.setattr(
        changed, "effective_sequence_in_transaction", lambda **_: (persistent_epoch, 2)
    )
    with pytest.raises(ApplicationError, match="invalid_publication_cursor"):
        changed.selected_snapshot_in_transaction(
            owner_id=owner, now=NOW, cursor=snapshot.next_cursor
        )
    for epoch in (snapshot.epoch, persistent_epoch):
        with pytest.raises(ApplicationError, match="publication_epoch_conflict"):
            changed.selected_changes_in_transaction(owner_id=owner, epoch=epoch, since=0, now=NOW)
    changes = reader.selected_changes_in_transaction(
        owner_id=owner, epoch=snapshot.epoch, since=0, now=NOW, limit=1
    )
    assert changes.epoch == snapshot.epoch and changes.sequence == 1 and changes.next_cursor
    ledger_query = next(q for q in queries if "publication_selected_changes" in str(q))
    assert persistent_epoch in ledger_query.compile().params.values()
    assert snapshot.epoch not in ledger_query.compile().params.values()
    scope = {"owner": owner, "type": "changes", "public_categories": same.public_categories}
    assert decode_cursor(changes.next_cursor, scope)["since"] == 1
    with pytest.raises(ApplicationError, match="invalid_publication_cursor"):
        decode_cursor(
            changes.next_cursor, {**scope, "public_categories": changed.public_categories}
        )
    monkeypatch.setattr(reader, "_live", lambda **_: {})
    removed = reader.selected_changes_in_transaction(
        owner_id=owner, epoch=snapshot.epoch, since=0, now=NOW
    )
    assert [c.operation for c in removed.changes] == ["remove", "remove"]
    assert all(c.item is None for c in removed.changes)


def test_edition_catalogue_rejects_one_excluded_fixed_member(monkeypatch):
    from publication.edition_catalogue import _index

    projections = [member(at=NOW).projection for _ in range(2)]
    references = [
        SimpleNamespace(content_id=p.content_id, content_version_id=p.content_version_id)
        for p in projections
    ]
    view = SimpleNamespace(
        valid=True,
        content=SimpleNamespace(entries=references, title="固定刊物"),
        kind="daily",
        key="2026-10-02",
        revision=1,
        created_at=NOW,
    )
    live = {p.content_id: (p, None) for p in projections}
    monkeypatch.setattr(PublicationReadingService, "_live", lambda self, **_: live)
    session = SimpleNamespace(scalars=lambda _: [])
    options = dict(owner_id=uuid4(), now=NOW, indexing_enabled=False, public_categories=("tip",))
    assert _index(session, view, **options) is not None
    live.pop(projections[1].content_id)
    assert _index(session, view, **options) is None


def test_edition_rss_fills_after_fifty_excluded_editions_and_still_caps_output(monkeypatch):
    from contextlib import contextmanager

    from publication.application import PublicationApplicationService

    seen = []

    @contextmanager
    def read(_self):
        yield None

    def edition(**kwargs):
        key = kwargs["key"]
        seen.append(key)
        if key < 50:
            raise ApplicationError("resource_not_found")
        return SimpleNamespace(key=key)

    monkeypatch.setattr(PublicationApplicationService, "_read", read)
    monkeypatch.setattr(
        "reports.edition_reading.iter_current_editions_in_transaction",
        lambda *a, **k: (SimpleNamespace(key=i) for i in range(120)),
    )
    monkeypatch.setattr("publication.application.render_edition_rss", lambda values, **_: values)
    application = PublicationApplicationService(None, public_categories=("tip",))
    monkeypatch.setattr(application, "edition", edition)
    result = application.edition_feed(owner_id=uuid4(), now=NOW)
    assert [view.key for view in result] == list(range(50, 100))
    assert seen == list(range(100))
