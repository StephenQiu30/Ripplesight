"""Bounded private files; PDF renders escaped local text with every request denied."""

import csv
import hashlib
import html
import io
import json
import time
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token
from playwright.sync_api import sync_playwright

from reports.export_schemas import EXPORT_MAX_BYTES, ExportDocument, ExportFormat

_FONT_HASH = "9ff3ce9439fe285cdabb46f9ceb46b1ac58f1ca07e6f4a764e8286db621a0af9"
_FONT_PATHS = (
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path(
        "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/"
        "86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc"
    ),
)


class ExportRenderError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    body: bytes
    mime_type: str
    extension: str

    @property
    def sha256(self) -> bytes:
        return hashlib.sha256(self.body).digest()


def csv_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value)
    # Spreadsheet programs may discard whitespace/control bytes before interpreting a formula.
    start = 0
    while start < len(text) and (
        text[start].isspace() or ord(text[start]) <= 32 or text[start] == "\ufeff"
    ):
        start += 1
    if text[start:].startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _local_markdown_html(markdown: str) -> str:
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = parser.parse(markdown)

    def sanitize(items: list[Token]) -> None:
        links: list[str] = []
        for token in items:
            if token.type == "image":
                token.content += f" ({token.attrGet('src') or ''})"
                token.type, token.tag, token.nesting, token.children = "text", "", 0, None
            elif token.type == "link_open":
                links.append(str(token.attrGet("href") or ""))
                token.type, token.tag, token.nesting, token.content = "text", "", 0, ""
            elif token.type == "link_close":
                token.type, token.tag, token.nesting = "text", "", 0
                token.content = f" ({links.pop()})" if links else ""
            if token.children is not None:
                sanitize(token.children)

    sanitize(tokens)
    return str(parser.renderer.render(tokens, parser.options, {}))


def render_export(
    document: ExportDocument, format: ExportFormat, *, deadline: float
) -> ExportArtifact:
    if time.monotonic() >= deadline:
        raise ExportRenderError("export_timeout")
    if len(document.markdown.encode()) > EXPORT_MAX_BYTES:
        raise ExportRenderError("export_size_exceeded")
    if format == "markdown":
        result = ExportArtifact(document.markdown.encode(), "text/markdown; charset=utf-8", "md")
    elif format == "json":
        body = json.dumps(
            document.model_dump(mode="json"), ensure_ascii=False, allow_nan=False, indent=2
        ).encode()
        result = ExportArtifact(body, "application/json; charset=utf-8", "json")
    elif format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\r\n")
        columns = (
            "content_id",
            "version_id",
            "source_key",
            "canonical_url",
            "title",
            "body",
            "author_name",
            "published_at",
            "discovered_at",
            "object_type",
            "text_scope",
            "input_observation_ids",
        )
        writer.writerow(columns)
        for row in document.rows:
            writer.writerow(csv_cell(row.get(column)) for column in columns)
            if stream.tell() > EXPORT_MAX_BYTES or time.monotonic() >= deadline:
                raise ExportRenderError(
                    "export_size_exceeded" if stream.tell() > EXPORT_MAX_BYTES else "export_timeout"
                )
        result = ExportArtifact(
            stream.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "csv"
        )
    else:
        if not any(
            path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == _FONT_HASH
            for path in _FONT_PATHS
        ):
            raise ExportRenderError("export_renderer_unavailable")
        # No provider HTML, images, scripts, links or file references are executable.
        source = (
            '<!doctype html><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "style-src 'unsafe-inline'; font-src 'none'; img-src 'none'; connect-src 'none'\">"
            '<style>@page{size:A4;margin:18mm}body{font-family:"PingFang SC",sans-serif;'
            "font-size:10pt;background:white;color:black;line-height:1.6;overflow-wrap:anywhere}"
            "h1{font-size:19pt;margin-bottom:18pt}h2{font-size:13pt;margin-top:18pt}"
            "h3{font-size:11pt}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
            "blockquote{margin-left:0;color:#555}table{border-collapse:collapse;width:100%}"
            "th,td{border-bottom:1px solid #ddd;padding:6pt;text-align:left}"
            "</style><title>"
            + html.escape(document.title)
            + "</title>"
            + _local_markdown_html(document.markdown)
        )
        with sync_playwright() as playwright:
            # Freeze the bundled revision; never download or use a signed-in browser.
            if "chromium-1243/" not in playwright.chromium.executable_path:
                raise ExportRenderError("export_renderer_unavailable")
            browser = playwright.chromium.launch(
                timeout=max(1, int((deadline - time.monotonic()) * 1000)),
                args=[
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-sync",
                    "--no-first-run",
                    "--host-resolver-rules=MAP * ~NOTFOUND",
                ],
            )
            try:
                context = browser.new_context(
                    java_script_enabled=False, service_workers="block", offline=True
                )
                context.route("**/*", lambda route: route.abort())
                page = context.new_page()
                page.set_default_timeout(max(1, int((deadline - time.monotonic()) * 1000)))
                page.set_content(source, wait_until="domcontentloaded")
                body = page.pdf(
                    format="A4",
                    print_background=True,
                )
                result = ExportArtifact(body, "application/pdf", "pdf")
            finally:
                browser.close()
    if time.monotonic() >= deadline:
        raise ExportRenderError("export_timeout")
    if not 1 <= len(result.body) <= EXPORT_MAX_BYTES:
        raise ExportRenderError("export_size_exceeded")
    return result
