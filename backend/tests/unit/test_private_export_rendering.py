import csv
import io
import json
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import reports.export_rendering as rendering
from core.config import Settings
from reports.export_rendering import ExportRenderError, csv_cell, render_export
from reports.export_schemas import EXPORT_MAX_BYTES, ContentExportInput, ExportDocument


def document() -> ExportDocument:
    return ExportDocument(
        kind="content",
        title="中文导出",
        manifest={"content_version_ids": ["fixed-version"], "published_at": None},
        markdown="# 中文导出\n\n原文引用 https://example.invalid/item\n<script>alert(1)</script>\n",
        rows=({"title": " \t=SUM(1,2)", "body": "中文正文", "published_at": None},),
    )


@pytest.mark.parametrize("format", ["markdown", "json", "csv", "pdf"])
def test_real_formats_or_explicit_pdf_unavailable_contract(format, tmp_path, record_property):
    try:
        artifact = render_export(document(), format, deadline=time.monotonic() + 120)
    except ExportRenderError as error:
        if format != "pdf" or error.code != "export_renderer_unavailable":
            raise
        record_property("pdf_result", "renderer_unavailable_no_artifact")
        assert not list(tmp_path.iterdir())
        return
    if format == "pdf":
        record_property("pdf_result", "actual_local_locked_renderer_file")
    path = tmp_path / f"private-export.{artifact.extension}"
    path.write_bytes(artifact.body)
    assert 1 <= path.stat().st_size <= EXPORT_MAX_BYTES
    if format == "markdown":
        assert "中文导出" in path.read_text()
    elif format == "json":
        decoded = json.loads(path.read_text())
        assert decoded["rows"][0]["published_at"] is None
        assert decoded["manifest"]["published_at"] is None
    elif format == "csv":
        row = next(csv.DictReader(io.StringIO(artifact.body.decode("utf-8-sig"))))
        assert row["title"] == "' \t=SUM(1,2)"
        assert row["published_at"] == "" and row["body"] == "中文正文"
    else:
        assert artifact.body.startswith(b"%PDF-") and b"%%EOF" in artifact.body[-40:]
        assert b"/ToUnicode" in artifact.body and b"/Type /Page" in artifact.body
        assert b"/JavaScript" not in artifact.body and b"/EmbeddedFile" not in artifact.body


@pytest.mark.parametrize(
    "value", ["=1+1", "+SUM(A1)", "-1+2", "@SUM(A1)", "\t=HYPERLINK('x')", "\r\n+1", "\ufeff@foo"]
)
def test_csv_formula_guard(value):
    assert csv_cell(value) == "'" + value
    assert csv_cell(None) == ""


def test_bounds_do_not_truncate():
    with pytest.raises(ExportRenderError, match="export_timeout"):
        render_export(document(), "markdown", deadline=time.monotonic() - 1)
    with pytest.raises(ExportRenderError, match="export_size_exceeded"):
        render_export(
            document().model_copy(update={"markdown": "x" * (EXPORT_MAX_BYTES + 1)}),
            "markdown",
            deadline=time.monotonic() + 120,
        )
    with pytest.raises(ValidationError):
        ContentExportInput(
            operation_id="00000000-0000-0000-0000-000000000001",
            content_version_ids=["00000000-0000-0000-0000-000000000001"] * 10001,
            format="csv",
        )
    settings = Settings(
        _env_file=None, database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test_unit"
    )
    assert settings.job_process_execution_timeout_seconds("report.export") == 120
    assert settings.job_process_execution_timeout_seconds("content.export") == 120


def test_missing_pinned_font_blocks_only_pdf(monkeypatch):
    monkeypatch.setattr(rendering, "_FONT_PATHS", ())
    assert csv_cell("normal value") == "normal value"
    for format in ("csv", "markdown", "json"):
        assert render_export(document(), format, deadline=time.monotonic() + 120).body
    with pytest.raises(ExportRenderError, match="export_renderer_unavailable"):
        render_export(document(), "pdf", deadline=time.monotonic() + 120)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("missing_binary", "export_renderer_unavailable"),
        ("launch_error", "export_renderer_unavailable"),
        ("launch_timeout", "export_timeout"),
    ],
)
def test_pinned_pdf_browser_failures_have_explicit_contract(
    monkeypatch, tmp_path, failure, expected
):
    font = tmp_path / "font.ttc"
    font.write_bytes(b"controlled font")
    monkeypatch.setattr(rendering, "_FONT_PATHS", (font,))
    monkeypatch.setattr(
        rendering, "_FONT_HASH", rendering.hashlib.sha256(font.read_bytes()).hexdigest()
    )
    executable = tmp_path / "chromium-1243" / "chrome"
    if failure != "missing_binary":
        executable.parent.mkdir()
        executable.touch()
    launches = []

    def launch(**kwargs):
        launches.append(kwargs)
        if failure == "launch_timeout":
            raise rendering.PlaywrightTimeoutError("controlled timeout")
        raise rendering.PlaywrightError("controlled unavailable browser")

    @contextmanager
    def playwright():
        yield SimpleNamespace(
            chromium=SimpleNamespace(executable_path=str(executable), launch=launch)
        )

    monkeypatch.setattr(rendering, "sync_playwright", playwright)
    with pytest.raises(ExportRenderError, match=expected):
        render_export(document(), "pdf", deadline=time.monotonic() + 120)
    if failure == "missing_binary":
        assert launches == []
    else:
        assert launches[0]["executable_path"] == str(executable)
        assert "--host-resolver-rules=MAP * ~NOTFOUND" in launches[0]["args"]


def test_pdf_markup_keeps_references_as_text_without_executable_provider_markup():
    markup = rendering._local_markdown_html(
        "# 中文标题\n[原文](https://example.invalid/source)\n"
        "![图片](file:///private/secret.png)\n<script>alert(1)</script>"
    )
    assert "<h1>中文标题</h1>" in markup
    assert "https://example.invalid/source" in markup
    assert "<img" not in markup and "<a " not in markup and "<script" not in markup
