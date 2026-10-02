from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from core.config import Settings
from knowledge.obsidian import (
    BEGIN,
    END,
    ObsidianWriteConflictError,
    daily_relative_path,
    write_daily_note,
)
from knowledge.schemas import DailyExportInput
from knowledge.services import KnowledgeExportService, daily_object_id, export_operation_id

OWNER_ID = UUID("10000000-0000-0000-0000-000000000001")
TOPIC_ID = UUID("20000000-0000-0000-0000-000000000001")
REPORT_ID = UUID("30000000-0000-0000-0000-000000000001")


def _note(*, title: str = "小米SU7", body: str = "# 日报\n初版") -> DailyExportInput:
    return DailyExportInput(
        owner_id=OWNER_ID,
        report_id=REPORT_ID,
        topic_id=TOPIC_ID,
        version=1,
        topic_name=title,
        window_start=datetime(2026, 9, 24, 16, tzinfo=UTC),
        generated_at=datetime(2026, 9, 25, 1, tzinfo=UTC),
        generator="template",
        body_markdown=body,
    )


def _object_id(note: DailyExportInput) -> UUID:
    return daily_object_id(
        owner_id=note.owner_id, topic_id=note.topic_id, window_start=note.window_start
    )


def test_first_export_writes_frontmatter_managed_block_and_user_notes(tmp_path: Path) -> None:
    note = _note()
    result = write_daily_note(tmp_path, "HotKey", note, _object_id(note))

    path = tmp_path / result.relative_path
    contents = path.read_text()
    assert result.relative_path == "HotKey/日报/2026-09-25 小米SU7.md"
    assert 'type: "daily"' in contents
    assert 'topic: "小米SU7"' in contents
    assert BEGIN in contents and END in contents
    assert "# 日报\n初版" in contents
    assert contents.endswith("## 我的笔记\n")


def test_reexport_preserves_user_content_outside_markers(tmp_path: Path) -> None:
    note = _note()
    first = write_daily_note(tmp_path, "HotKey", note, _object_id(note))
    path = tmp_path / first.relative_path
    path.write_text(path.read_text().replace("## 我的笔记\n", "## 我的笔记\n保留这段。\n"))

    updated = note.model_copy(update={"body_markdown": "# 日报\n第二版"})
    result = write_daily_note(tmp_path, "HotKey", updated, _object_id(note))

    contents = path.read_text()
    assert result.written
    assert "第二版" in contents
    assert "初版" not in contents
    assert contents.endswith("## 我的笔记\n保留这段。\n")


def test_same_content_does_not_change_mtime(tmp_path: Path) -> None:
    note = _note()
    first = write_daily_note(tmp_path, "HotKey", note, _object_id(note))
    path = tmp_path / first.relative_path
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))

    second = write_daily_note(tmp_path, "HotKey", note, _object_id(note))

    assert not second.written
    assert second.content_sha256 == first.content_sha256
    assert path.stat().st_mtime_ns == 1_000_000_000


def test_user_edit_during_prepared_write_survives_and_temporary_file_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    note = _note()
    first = write_daily_note(tmp_path, "HotKey", note, _object_id(note))
    target = tmp_path / first.relative_path
    user_text = target.read_text() + "\n刚写的个人笔记。\n"
    original_fsync = os.fsync

    def edit_during_fsync(fd: int) -> None:
        original_fsync(fd)
        target.write_text(user_text)

    monkeypatch.setattr(os, "fsync", edit_during_fsync)
    with pytest.raises(ObsidianWriteConflictError, match="changed before replacement"):
        write_daily_note(
            tmp_path,
            "HotKey",
            note.model_copy(update={"body_markdown": "第二版"}),
            _object_id(note),
            expected_content_sha256=first.content_sha256,
        )
    assert target.read_text() == user_text
    assert not list(target.parent.glob(".hotkey-*"))


def test_manual_managed_block_edit_is_not_overwritten_but_saved_export_can_replay(
    tmp_path: Path,
) -> None:
    note = _note()
    first = write_daily_note(tmp_path, "HotKey", note, _object_id(note))
    target = tmp_path / first.relative_path
    manual = target.read_text().replace("初版", "人工改动")
    target.write_text(manual)
    with pytest.raises(ObsidianWriteConflictError, match="recorded export"):
        write_daily_note(
            tmp_path,
            "HotKey",
            note.model_copy(update={"body_markdown": "第二版"}),
            _object_id(note),
            expected_content_sha256=first.content_sha256,
        )
    assert target.read_text() == manual
    # A successful file write preceding a DB rollback is a recoverable receipt.
    target.write_text(manual.replace("人工改动", "初版"))
    updated = note.model_copy(update={"body_markdown": "第二版"})
    written = write_daily_note(
        tmp_path,
        "HotKey",
        updated,
        _object_id(note),
        expected_content_sha256=first.content_sha256,
    )
    assert written.written
    replay = write_daily_note(
        tmp_path,
        "HotKey",
        updated,
        _object_id(note),
        expected_content_sha256=first.content_sha256,
    )
    assert not replay.written and replay.content_sha256 == written.content_sha256


def test_title_path_separators_and_parent_components_are_sanitized(tmp_path: Path) -> None:
    note = _note(title="../机型/热点\\跟踪")
    relative = daily_relative_path(note)
    result = write_daily_note(tmp_path, "HotKey", note, _object_id(note))

    assert relative.parent == Path("日报")
    assert ".." not in relative.name
    assert "/" not in relative.name
    assert (
        (tmp_path / result.relative_path).resolve().is_relative_to((tmp_path / "HotKey").resolve())
    )


def test_existing_unmanaged_name_gets_short_id_without_overwrite(tmp_path: Path) -> None:
    note = _note()
    expected = tmp_path / "HotKey" / daily_relative_path(note)
    expected.parent.mkdir(parents=True)
    expected.write_text("这是用户自己的文件")

    result = write_daily_note(tmp_path, "HotKey", note, _object_id(note))

    assert result.relative_path.endswith("-20000000.md")
    assert expected.read_text() == "这是用户自己的文件"


def test_symbolic_link_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    root = vault / "HotKey"
    root.mkdir()
    (root / "日报").symlink_to(outside, target_is_directory=True)
    note = _note()

    with pytest.raises(OSError, match="symbolic link"):
        write_daily_note(vault, "HotKey", note, _object_id(note))
    assert list(outside.iterdir()) == []


def test_unwritable_vault_fails_without_creating_root(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    vault.chmod(0o500)
    try:
        note = _note()
        with pytest.raises(PermissionError, match="not writable"):
            write_daily_note(vault, "HotKey", note, _object_id(note))
        assert not (vault / "HotKey").exists()
    finally:
        vault.chmod(0o700)


def test_disabled_scan_accepts_nothing_and_operation_id_tracks_version() -> None:
    settings = Settings(database_url="postgresql://local/unused", obsidian_enabled=False)
    service = KnowledgeExportService(cast(Session, object()), settings)

    assert service.enqueue_due_in_transaction(now=datetime.now(UTC)) == 0
    assert export_operation_id(report_id=REPORT_ID, version=1) != export_operation_id(
        report_id=REPORT_ID, version=2
    )
