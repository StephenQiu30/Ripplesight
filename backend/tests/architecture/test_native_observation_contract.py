"""Native sharing must preserve actual source, ownership, and strict legacy persistence."""

from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from content.models import ContentNativeIdentity, ContentObservation, ContentObservationInput
from events.models import EventMember


def test_native_identity_map_and_observation_edges_have_owner_scoped_foreign_keys():
    native = ContentNativeIdentity.__table__
    assert any(
        isinstance(item, UniqueConstraint)
        and tuple(item.columns.keys())
        == ("owner_id", "platform", "object_type", "namespace", "native_id")
        for item in native.constraints
    )
    edges = ContentObservationInput.__table__
    assert tuple(edges.primary_key.columns.keys()) == (
        "owner_id",
        "output_observation_id",
        "input_observation_id",
    )
    fk = {item.name: item for item in edges.constraints if isinstance(item, ForeignKeyConstraint)}
    assert fk["content_observation_inputs_output_fkey"].ondelete == "CASCADE"
    assert fk["content_observation_inputs_input_fkey"].ondelete == "RESTRICT"
    assert all("owner_id" in item.columns for item in fk.values())


def test_modern_provenance_is_complete_but_legacy_null_and_record_source_are_preserved():
    table = ContentObservation.__table__
    assert table.c.input_basis.nullable and table.c.native_identity_proof.nullable
    checks = {
        item.name: str(item.sqltext)
        for item in table.constraints
        if isinstance(item, CheckConstraint)
    }
    provenance = checks["content_observations_provenance_check"]
    assert "input_basis IS NULL AND source_key IS NULL" in provenance
    for name in ("source_key", "source_external_id", "source_identity_basis"):
        assert f"{name} IS NOT NULL" in provenance
    member = EventMember.__table__
    foreign_keys = {
        item.name: item for item in member.constraints if isinstance(item, ForeignKeyConstraint)
    }
    assert "event_members_content_source_fkey" not in foreign_keys
    actual = foreign_keys["event_members_observation_source_fkey"]
    assert tuple(actual.columns.keys()) == (
        "owner_id",
        "observation_id",
        "content_id",
        "content_version_id",
        "observation_source_key",
    )
    assert member.c.observation_id.nullable and member.c.input_manifest.nullable


def test_canonical_schema_keeps_old_defaults_and_new_content_contract():
    schema = (Path(__file__).resolve().parents[2] / "database/schema.sql").read_text()
    for name in ("content_native_identities", "content_observation_inputs"):
        assert f"CREATE TABLE {name} (" in schema
    assert "content_observations_source_context_key UNIQUE" in schema
    assert "event_members_observation_source_fkey FOREIGN KEY" in schema
    assert "viewpoints JSONB DEFAULT '[]'::jsonb NOT NULL" in schema
    assert "diagnostic_history JSONB DEFAULT '[]'::jsonb NOT NULL" in schema
    assert "expected_event_revisions JSONB DEFAULT '{}'::jsonb NOT NULL" in schema
    assert "status VARCHAR(16) DEFAULT 'pending' NOT NULL" in schema
