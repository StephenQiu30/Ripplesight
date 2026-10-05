from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from analysis.editorial_models import EditorialContentState, EditorialRun, EditorialSourceVersion
from analysis.editorial_services import EditorialService
from content.schemas import EventContentReadReference

NOW = datetime(2026, 10, 5, tzinfo=UTC)


@pytest.mark.parametrize("has_completed_history", [True, False])
def test_template_change_scans_completed_history_independently_of_current_pointer(
    monkeypatch: pytest.MonkeyPatch, has_completed_history: bool
) -> None:
    owner, content, version = UUID(int=1), UUID(int=2), UUID(int=3)
    source = SimpleNamespace(
        owner_id=owner,
        source_key="x",
        revision=2,
        configuration={"enabled": True},
        scan_cursor=None,
    )
    reference = EventContentReadReference(content_id=content, content_version_id=version)
    session = MagicMock()
    session.scalars.return_value = [source]
    # Even a failed current explicit evaluation cannot erase an older completed input.
    session.get.side_effect = [
        SimpleNamespace(current_run_id=UUID(int=4), manual_version=0),
        SimpleNamespace(status="failed", result=None),
    ]
    session.scalar.side_effect = [None, UUID(int=5) if has_completed_history else None]
    monkeypatch.setattr(
        "analysis.editorial_services.pipeline_version", lambda: "editorial@new-hash"
    )
    monkeypatch.setattr(
        "analysis.editorial_services.latest_editorial_references_in_transaction",
        lambda *args, **kwargs: [reference],
    )
    request = MagicMock()
    monkeypatch.setattr(EditorialService, "request_run_in_transaction", request)
    assert EditorialService(session).enqueue_due_in_transaction(now=NOW) == (
        0 if has_completed_history else 1
    )
    assert request.call_count == (0 if has_completed_history else 1)
    query = session.scalar.call_args_list[1].args[0].compile()
    assert query.params == {
        "owner_id_1": owner,
        "content_id_1": content,
        "content_version_id_1": version,
        "source_key_1": "x",
        "source_revision_1": 2,
        "stages_1": "all",
        "status_1": ["complete", "blocked"],
        "param_1": 1,
    }


def test_manual_correction_still_blocks_background_admission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session.scalars.return_value = [
        SimpleNamespace(
            owner_id=UUID(int=1),
            source_key="x",
            revision=1,
            configuration={"enabled": True},
            scan_cursor=None,
        )
    ]
    session.scalar.return_value = None
    session.get.side_effect = [
        SimpleNamespace(current_run_id=UUID(int=4)),
        SimpleNamespace(result={"manual": True}),
    ]
    reference = EventContentReadReference(content_id=UUID(int=2), content_version_id=UUID(int=3))
    monkeypatch.setattr(
        "analysis.editorial_services.latest_editorial_references_in_transaction",
        lambda *args, **kwargs: [reference],
    )
    request = MagicMock()
    monkeypatch.setattr(EditorialService, "request_run_in_transaction", request)
    assert EditorialService(session).enqueue_due_in_transaction(now=NOW) == 0
    request.assert_not_called()
    assert session.get.call_args_list[0].args[0] is EditorialContentState
    assert session.get.call_args_list[1].args[0] is EditorialRun


def test_quoted_title_is_not_loaded_as_original_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    observation = SimpleNamespace(
        id=UUID(int=4),
        content_version=SimpleNamespace(
            title="Main title", body="Original main post.", text_scope=SimpleNamespace(value="full")
        ),
        author_external_id=None,
        canonical_url=None,
        final_url=None,
        published_at=None,
        received_at=NOW,
    )
    main = SimpleNamespace(source_key="x", observation=observation)
    quoted = SimpleNamespace(
        observation=SimpleNamespace(
            content_version=SimpleNamespace(body=None, title="Title-only quoted evidence"),
            author_external_id="quoted author",
        )
    )
    frozen = MagicMock(side_effect=[main, quoted])
    monkeypatch.setattr(
        "analysis.editorial_services.frozen_editorial_content_in_transaction", frozen
    )
    monkeypatch.setattr(
        "analysis.editorial_services.editorial_first_received_at_in_transaction",
        lambda *args, **kwargs: NOW,
    )
    profile = SimpleNamespace(
        configuration={
            "name": "Original publisher",
            "source_kind": "x_search",
            "tier": "T1",
            "first_party": False,
            "owner_entity_id": None,
            "tags": [],
        }
    )
    session = MagicMock()
    session.get.return_value = profile
    run = EditorialRun(
        owner_id=UUID(int=1),
        content_id=UUID(int=2),
        content_version_id=UUID(int=3),
        source_key="x",
        source_revision=1,
        input_manifest={
            "quote": {"content_id": str(UUID(int=5)), "content_version_id": str(UUID(int=6))}
        },
    )
    item = EditorialService(session, clock=lambda: NOW)._load_material(run)
    assert item.body == "Original main post." and item.quoted_text == ""
    assert session.get.call_args.args[0] is EditorialSourceVersion
