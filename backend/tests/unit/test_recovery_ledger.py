"""Test corruption and independent pin boundaries before any restore I/O."""

import json
import os
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from typer.testing import CliRunner

from backups import restore
from backups.schemas import EvidenceObjectInventory, EvidenceObjectState
from cli import commands
from core.config import Settings
from evidence.journal_contract import (
    RecoveryLedgerError,
    RecoverySnapshot,
    entry_digest,
    genesis_digest,
    verify_recovery_inputs,
)
from tests.recovery_fixtures import recovery_sample
from tests.unit.test_backup_restore import NOW, _manifest


@pytest.mark.parametrize("empty", [False, True])
def test_complete_export_matches_independent_pin(tmp_path: Path, empty: bool) -> None:
    manifest = _manifest()
    targets = () if empty else ((uuid4(), "content_item", uuid4()),)
    snapshot, checkpoint = recovery_sample(manifest, targets)
    path = tmp_path / "snapshot.json"
    path.write_text(snapshot.model_dump_json())
    path.chmod(0o600)
    verified = verify_recovery_inputs(
        snapshot_path=path, checkpoint_json=checkpoint.model_dump_json(), manifest=manifest
    )
    assert verified.snapshot == snapshot and verified.checkpoint == checkpoint


@pytest.mark.parametrize(
    "defect",
    [
        "tail",
        "gap",
        "changed_owner",
        "previous",
        "digest",
        "action",
        "reason",
        "naive_time",
        "format",
        "normalization",
        "extra",
        "duplicate_operation",
        "ledger",
        "epoch",
        "backup",
        "archive",
        "schema",
        "head_sequence",
        "head_digest",
        "missing_checkpoint",
        "boolean_sequence",
        "duplicate_key",
    ],
)
def test_bad_export_rejected_before_creating_any_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    manifest = _manifest()
    snapshot, checkpoint = recovery_sample(
        manifest, [(uuid4(), "content_item", uuid4()), (uuid4(), "content_item", uuid4())]
    )
    if defect == "duplicate_operation":
        owner = uuid4()
        snapshot, checkpoint = recovery_sample(
            manifest, [(owner, "content_item", uuid4())] * 2, operation_id=uuid4()
        )
    export, pin = snapshot.model_dump(mode="json"), checkpoint.model_dump(mode="json")
    first = export["entries"][0]
    if defect == "tail":
        export["entries"].pop()
    elif defect == "gap":
        first["sequence"] = 2
    elif defect == "changed_owner":
        first["owner_id"] = str(uuid4())
    elif defect == "previous":
        first["previous_digest"] = "0" * 64
    elif defect == "digest":
        first["digest"] = "0" * 64
    elif defect == "action":
        first["action"] = "allow_resource"
    elif defect == "reason":
        first["reason"] = "unknown"
    elif defect == "naive_time":
        first["occurred_at"] = "2026-10-12T00:00:00"
    elif defect == "format":
        export["format_version"] = "unrecognized"
    elif defect == "normalization":
        export["normalization_version"] = "native_guess.v1"
    elif defect == "extra":
        first["password"] = "must-not-be-exposed"
    elif defect in {
        "ledger",
        "epoch",
        "backup",
        "archive",
        "schema",
        "head_sequence",
        "head_digest",
    }:
        field = {
            "ledger": "ledger_id",
            "backup": "backup_id",
            "archive": "archive_sha256",
            "schema": "schema_sha256",
        }.get(defect, defect)
        pin[field] = (
            str(uuid4())
            if field.endswith("_id")
            else 99
            if field in {"epoch", "head_sequence"}
            else "f" * 64
        )
    elif defect == "boolean_sequence":
        first["sequence"] = True
    serialized = json.dumps(export)
    if defect == "duplicate_key":
        serialized = '{"epoch":1,' + serialized[1:]
    path = tmp_path / "snapshot.json"
    path.write_text(serialized)
    path.chmod(0o600)
    engine = MagicMock()
    monkeypatch.setattr(restore, "create_engine", engine)
    service = restore.BackupRestoreService(
        source_database_url="postgresql+psycopg://127.0.0.1/hotkey_test_source",
        isolation_database_url="postgresql+psycopg://127.0.0.1/postgres",
        schema_path=tmp_path / "schema.sql",
    )
    monkeypatch.setattr(service, "check_candidate", lambda _: (manifest, tmp_path / "dump"))
    with pytest.raises(restore.BackupRestoreError) as error:
        service.verify_replay(
            tmp_path,
            snapshot_path=path,
            checkpoint_json="" if defect == "missing_checkpoint" else json.dumps(pin),
        )
    assert "must-not-be-exposed" not in str(error.value)
    engine.assert_not_called()


@pytest.mark.parametrize("defect", ["mode", "link", "missing", "directory", "fifo", "size"])
def test_snapshot_file_is_private_regular_and_bounded(tmp_path: Path, defect: str) -> None:
    manifest = _manifest()
    snapshot, pin = recovery_sample(manifest)
    path = tmp_path / "snapshot.json"
    path.write_text(snapshot.model_dump_json())
    path.chmod(0o600)
    if defect == "mode":
        path.chmod(0o644)
    elif defect == "link":
        linked = tmp_path / "link"
        linked.symlink_to(path)
        path = linked
    elif defect == "missing":
        path.unlink()
    elif defect == "directory":
        path.unlink()
        path.mkdir(mode=0o600)
    elif defect == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    else:
        with path.open("wb") as handle:
            handle.truncate(16 * 1024 * 1024 + 1)
    with pytest.raises(RecoveryLedgerError):
        verify_recovery_inputs(
            snapshot_path=path, checkpoint_json=pin.model_dump_json(), manifest=manifest
        )


def test_replay_rejects_even_inventory_only_objects_before_database_or_object_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(
        evidence_objects=(
            EvidenceObjectInventory(
                resource_record_id=uuid4(),
                object_name="private/evidence",
                expires_at=NOW + timedelta(days=1),
                state=EvidenceObjectState.PRESENT,
                checked_at=NOW,
                size_bytes=1,
                etag="controlled-etag",
                last_modified_at=NOW,
            ),
        )
    )
    engine, objects = MagicMock(), MagicMock()
    monkeypatch.setattr(restore, "create_engine", engine)
    service = restore.BackupRestoreService(
        source_database_url="postgresql+psycopg://127.0.0.1/hotkey_test_source",
        isolation_database_url="postgresql+psycopg://127.0.0.1/postgres",
        schema_path=tmp_path / "schema.sql",
        evidence_restore_verifier=objects,
    )
    monkeypatch.setattr(service, "check_candidate", lambda _: (manifest, tmp_path / "dump"))
    with pytest.raises(restore.BackupRestoreError, match="without objects"):
        service.verify_replay(tmp_path, snapshot_path=tmp_path / "absent.json", checkpoint_json="")
    engine.assert_not_called()
    objects.verify.assert_not_called()


def test_canonical_hash_binds_ledger_and_normalizes_time() -> None:
    snapshot = RecoverySnapshot(
        format_version="ripplesight.recovery-ledger.v1",
        ledger_id=UUID("00000000-0000-4000-8000-000000000001"),
        epoch=1,
        normalization_version="resource_uuid.v1",
        entries=(),
    )
    import hashlib

    expected = hashlib.sha256(
        b'ripplesight.recovery.genesis.v1\0{"epoch":1,'
        b'"ledger_id":"00000000-0000-4000-8000-000000000001",'
        b'"normalization_version":"resource_uuid.v1"}'
    ).hexdigest()
    assert genesis_digest(snapshot) == expected
    sample, _ = recovery_sample(_manifest(), [(uuid4(), "content_item", uuid4())])
    utc = datetime(2026, 10, 12, 1, 2, 3, 4, tzinfo=UTC)
    entry = sample.entries[0].model_copy(update={"occurred_at": utc})
    equivalent = entry.model_copy(
        update={"occurred_at": utc.astimezone(timezone(timedelta(hours=8)))}
    )
    # Real parsing normalizes the alternate timezone, not model_copy's bypass.
    equivalent = type(entry).model_validate_json(equivalent.model_dump_json())
    assert entry_digest(entry) == entry_digest(equivalent)


@pytest.mark.parametrize("case", ["missing", "bad_name", "success"])
def test_replay_cli_requires_independent_inputs_and_never_promises_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    path = tmp_path / "snapshot.json"
    path.touch(mode=0o600)
    service = MagicMock()
    result = service.verify_replay.return_value
    result.service_open_permitted = False
    result.duration_seconds = 0.1
    monkeypatch.setattr(commands, "BackupRestoreService", lambda **_: service)
    monkeypatch.setattr(
        commands,
        "get_settings",
        lambda: Settings(database_url="postgresql+psycopg://127.0.0.1/hotkey_test_cli"),
    )
    monkeypatch.delenv("CONTROLLED_PIN", raising=False)
    monkeypatch.delenv("CONTROLLED_RESTORE", raising=False)
    if case == "success":
        monkeypatch.setenv("CONTROLLED_PIN", "independent-controlled-pin")
        monkeypatch.setenv("CONTROLLED_RESTORE", "controlled-isolation-url")
    invocation = [
        "backup",
        "verify-replay",
        "--candidate",
        str(tmp_path),
        "--ledger-snapshot",
        str(path),
        "--checkpoint-env",
        "bad-name" if case == "bad_name" else "CONTROLLED_PIN",
        "--isolation-url-env",
        "CONTROLLED_RESTORE",
    ]
    output = CliRunner().invoke(commands.app, invocation)
    if case == "success":
        assert output.exit_code == 0, output.output
        assert "service open permitted: false" in output.output
        assert "independent-controlled-pin" not in output.output
        service.verify_replay.assert_called_once()
    else:
        assert output.exit_code == 1
        service.verify_replay.assert_not_called()
