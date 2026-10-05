"""Strict source parsing/collection contracts; credentials never enter these models."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Literal, Self
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from uuid import UUID

from pydantic import Field, JsonValue, field_validator, model_validator

from sources.adapters.rsshub_endpoint import RSSHUB_HOSTS
from sources.adapters.web_targets import normalize_public_article_url, normalize_web_host
from sources.editorial_base import EditorialContract as EditorialContract
from sources.editorial_body_review import EditorialBodyReview
from sources.editorial_identity import EditorialNativeIdentityProof
from sources.editorial_rsshub import EditorialRsshubConfiguration

type EditorialSourceKind = Literal[
    "rss", "web_list", "json_list", "x_search", "mp_account", "external"
]
type ParticipationMode = Literal["editorial", "hot_signal", "isolated"]
_SECRET_KEYS = frozenset(
    {"authorization", "cookie", "password", "secret", "token", "api_key", "apikey", "access_token"}
)
_MATERIAL_META_RESERVED = frozenset(
    {
        "body",
        "bodytext",
        "bodyhtml",
        "bodymarkdown",
        "raw",
        "rawtext",
        "rawhtml",
        "html",
        "markdown",
        "text",
        "content",
        "media",
        "mediadetails",
        "license",
        "licence",
        "permission",
        "permissions",
        "authorized",
        "approved",
        "allowsitefulltext",
        "allowsyndication",
        "allowpublic",
        "nativeidentity",
        "identityproof",
    }
)


def public_url(value: str, *, keep_fragment: bool = False) -> str:
    if any(key.casefold() in _SECRET_KEYS for key, _ in parse_qsl(urlsplit(value).query)):
        raise ValueError("credentials must stay in server execution context")
    normalized = normalize_public_article_url(value)
    if keep_fragment and (fragment := urlsplit(value).fragment):
        if len(fragment) > 256 or any(ord(char) < 32 for char in fragment):
            raise ValueError("invalid public URL fragment")
        parts = urlsplit(normalized)
        return urlunsplit((*parts[:4], fragment))
    return normalized


def non_secret_json(value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode()) > 65_536:
        raise ValueError("JSON metadata exceeds its limit")

    def check(node: object, depth: int = 0) -> None:
        if depth > 12:
            raise ValueError("JSON metadata is too deep")
        if isinstance(node, dict):
            for key, child in node.items():
                if str(key).casefold() in _SECRET_KEYS:
                    raise ValueError("credentials must stay in server execution context")
                check(child, depth + 1)
        elif isinstance(node, (list, tuple)):
            if len(node) > 1000:
                raise ValueError("JSON metadata array exceeds its limit")
            for child in node:
                check(child, depth + 1)

    check(value)


def fingerprint(value: object) -> bytes:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).digest()


class NoiseFilter(EditorialContract):
    drop_markers: tuple[str, ...] = Field(default=(), max_length=100)
    drop_markers_title_only: tuple[str, ...] = Field(default=(), max_length=100)
    keep_if_matches: tuple[str, ...] = Field(default=(), max_length=100)

    @field_validator("drop_markers", "drop_markers_title_only", "keep_if_matches")
    @classmethod
    def bounded_words(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not word.strip() or len(word) > 128 for word in value):
            raise ValueError("noise markers must be bounded and non-empty")
        return value


class PrefixRewrite(EditorialContract):
    from_prefix: str = Field(max_length=2048)
    to_prefix: str = Field(max_length=2048)

    @field_validator("from_prefix", "to_prefix")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return public_url(value)


class BooleanCondition(EditorialContract):
    path: str = Field(min_length=1, max_length=256)
    equals: bool


class NumericCondition(EditorialContract):
    path: str = Field(min_length=1, max_length=256)
    min: float = Field(allow_inf_nan=False)


class DetailConfiguration(EditorialContract):
    max_fetches: int = Field(default=0, ge=0, le=20)
    published_at_selector: str | None = Field(default=None, max_length=512)
    published_at_regex: str | None = Field(default=None, max_length=512)
    published_at_utc_offset: str = Field(default="+08:00", pattern=r"^[+-](?:0\d|1[0-4]):[0-5]\d$")
    published_at_authoritative: bool = False
    upgrade_date_precision: bool = False
    title_selector: str | None = Field(default=None, max_length=512)
    title_regex: str | None = Field(default=None, max_length=512)
    title_authoritative: bool = False
    summary_selector: str | None = Field(default=None, max_length=512)


class EditorialBodyConfiguration(EditorialContract):
    enabled: bool = False
    required: bool = True
    max_fetches: int = Field(default=5, ge=1, le=20)
    max_target_requests: int = Field(default=5, ge=1, le=20)
    timeout_seconds: int = Field(default=20, ge=1, le=20)
    max_response_bytes: int = Field(default=2 * 1024 * 1024, ge=1, le=2 * 1024 * 1024)
    max_content_characters: int = Field(default=100_000, ge=1, le=100_000)
    allowed_hosts: tuple[str, ...] = Field(min_length=1, max_length=32)
    review: EditorialBodyReview | None = None

    @field_validator("allowed_hosts")
    @classmethod
    def exact_public_hosts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(normalize_web_host(host) for host in value))
        if len(set(normalized)) != len(normalized):
            raise ValueError("body hosts must be unique exact public domains")
        return normalized


class EditorialSourceConfiguration(EditorialContract):
    kind: EditorialSourceKind
    allowed_hosts: tuple[str, ...] = Field(default=(), max_length=32)
    allow_url_prefixes: tuple[str, ...] = Field(default=(), max_length=100)
    deny_url_prefixes: tuple[str, ...] = Field(default=(), max_length=100)
    ingest_noise_filter: NoiseFilter | None = None
    require_any_terms: tuple[str, ...] = Field(default=(), max_length=100)
    summary_max_chars: int | None = Field(default=None, ge=1, le=4000, strict=True)
    item_url_prefix_rewrite: PrefixRewrite | None = None
    sort_by_published_at: bool = False
    detail: DetailConfiguration | None = None
    fetch_public_content: bool = False
    body_extraction: EditorialBodyConfiguration | None = None
    initial_backfill_limit: int = Field(default=30, ge=1, le=200)
    initial_backfill_months: int = Field(default=12, ge=1, le=24)
    feed_url: str | None = Field(default=None, max_length=2048)
    rsshub: EditorialRsshubConfiguration | None = None
    summary_is_body: bool = False
    preserve_url_fragment: bool = False
    allow_categories: tuple[str, ...] = Field(default=(), max_length=100)
    deny_categories: tuple[str, ...] = Field(default=(), max_length=100)
    url: str | None = Field(default=None, max_length=2048)
    base_url: str | None = Field(default=None, max_length=2048)
    parse_mode: Literal["html", "markdown", "docusaurus_changelog"] = "html"
    adapter: Literal["mimo_home"] | None = None
    cache_tolerance_seconds: int = Field(default=0, ge=0, le=86_400)
    links_start_line: bool = False
    item_selector: str | None = Field(default=None, max_length=512)
    link_selector: str | None = Field(default=None, max_length=512)
    title_selector: str | None = Field(default=None, max_length=512)
    published_at_selector: str | None = Field(default=None, max_length=512)
    published_at_regex: str | None = Field(default=None, max_length=512)
    published_at_utc_offset: str = Field(default="+08:00", pattern=r"^[+-](?:0\d|1[0-4]):[0-5]\d$")
    mode: Literal["json", "html_json_key", "html_window_var"] = "json"
    method: Literal["GET", "POST"] = "GET"
    headers: dict[str, str] = Field(default_factory=dict, max_length=8)
    body_json: JsonValue | None = None
    json_key: str | None = Field(default=None, max_length=128)
    window_var: str | None = Field(default=None, pattern=r"^[A-Za-z_$][A-Za-z0-9_$]{0,127}$")
    items_path: str | None = Field(default=None, max_length=256)
    items_object_values: bool = False
    title_paths: tuple[str, ...] = Field(default=(), max_length=16)
    summary_paths: tuple[str, ...] = Field(default=(), max_length=16)
    author_paths: tuple[str, ...] = Field(default=(), max_length=16)
    published_at_path: str = Field(default="", max_length=256)
    published_at_unit: Literal["iso", "epoch_ms", "epoch_s", "yyyymmdd"] = "iso"
    external_id_path: str | None = Field(default=None, max_length=256)
    url_template: str | None = Field(default=None, max_length=2048)
    url_template_fallback: str | None = Field(default=None, max_length=2048)
    raw_drop_keys: tuple[str, ...] = Field(default=(), max_length=100)
    require_boolean: BooleanCondition | None = None
    min_numeric: NumericCondition | None = None
    query: str | None = Field(default=None, min_length=1, max_length=1024)
    search_type: Literal["Latest", "Top"] = "Latest"
    wxid: str | None = Field(default=None, max_length=128)
    ghid: str | None = Field(default=None, max_length=128)
    nickname: str | None = Field(default=None, max_length=128)

    @field_validator("require_any_terms")
    @classmethod
    def bounded_required_terms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(" ".join(unicodedata.normalize("NFKC", term).split()) for term in value)
        if any(len(term) > 128 for term in value) or any(
            not term or len(term) > 128 for term in normalized
        ):
            raise ValueError("required terms must be bounded and non-empty")
        return normalized

    @model_validator(mode="after")
    def validate_kind_contract(self) -> Self:
        common = {"kind", "allowed_hosts", "initial_backfill_limit", "initial_backfill_months"}
        collected = {
            "allow_url_prefixes",
            "deny_url_prefixes",
            "ingest_noise_filter",
            "item_url_prefix_rewrite",
            "sort_by_published_at",
            "detail",
            "fetch_public_content",
            "body_extraction",
        }
        allowed = {
            "rss": collected
            | {
                "feed_url",
                "rsshub",
                "summary_is_body",
                "preserve_url_fragment",
                "allow_categories",
                "deny_categories",
                "published_at_utc_offset",
                "require_any_terms",
                "summary_max_chars",
            },
            "web_list": collected
            | {
                "url",
                "base_url",
                "parse_mode",
                "adapter",
                "cache_tolerance_seconds",
                "links_start_line",
                "preserve_url_fragment",
                "item_selector",
                "link_selector",
                "title_selector",
                "published_at_selector",
                "published_at_regex",
                "published_at_utc_offset",
            },
            "json_list": collected
            | {
                "url",
                "mode",
                "method",
                "headers",
                "body_json",
                "json_key",
                "window_var",
                "items_path",
                "items_object_values",
                "title_paths",
                "summary_paths",
                "summary_is_body",
                "author_paths",
                "published_at_path",
                "published_at_unit",
                "published_at_utc_offset",
                "external_id_path",
                "url_template",
                "url_template_fallback",
                "raw_drop_keys",
                "require_boolean",
                "min_numeric",
                "require_any_terms",
                "summary_max_chars",
            },
            "x_search": {"query", "search_type", "ingest_noise_filter", "item_url_prefix_rewrite"},
            "mp_account": {"wxid", "ghid", "nickname"},
            "external": set(),
        }
        unexpected = self.model_fields_set - common - allowed[self.kind]
        for name in unexpected:
            field = type(self).model_fields[name]
            default = field.get_default(call_default_factory=True, validated_data={})
            if getattr(self, name) != default:
                raise ValueError("unsupported fields for this source kind")
        if self.rsshub is not None:
            if self.kind != "rss" or len(self.allowed_hosts) != 1:
                raise ValueError("local RSSHub mode requires exactly one local RSS host")
            host = self.allowed_hosts[0]
            if host not in RSSHUB_HOSTS or self.feed_url != self.rsshub.endpoint(host):
                raise ValueError("RSSHub endpoint must exactly match its frozen local contract")
            if self.detail is not None or self.fetch_public_content or self.item_url_prefix_rewrite:
                raise ValueError("RSSHub mode forbids implicit remote detail or URL rewriting")
            if self.summary_is_body or self.preserve_url_fragment:
                raise ValueError(
                    "RSSHub text scope is explicit; generic RSS full-text flags are unsupported"
                )
            if self.initial_backfill_limit > self.rsshub.max_items:
                raise ValueError("initial RSSHub backfill exceeds the frozen item bound")
            return self
        normalized = tuple(sorted(normalize_web_host(host) for host in self.allowed_hosts))
        if len(set(normalized)) != len(normalized):
            raise ValueError("source hosts must be unique exact domains")
        if self.kind in {"rss", "web_list", "json_list"} and not normalized:
            raise ValueError("network source needs exact allowed hosts")
        target = self.feed_url if self.kind == "rss" else self.url
        if self.kind in {"rss", "web_list", "json_list"} and not target:
            raise ValueError("source URL is required")
        for url in (target, self.base_url):
            if url:
                public_url(url)
                if urlsplit(url).hostname not in normalized:
                    raise ValueError("source URL is outside approved hosts")
        if target and target.startswith("https://r.jina.ai/"):
            if self.kind != "web_list":
                raise ValueError("Jina is only an explicit web listing transport")
            embedded = public_url(target.removeprefix("https://r.jina.ai/"))
            if urlsplit(embedded).hostname not in normalized:
                raise ValueError("Jina target requires its own approved host")
        for header, value in self.headers.items():
            if (
                header.casefold()
                not in {"accept", "content-type", "x-requested-with", "x-github-api-version"}
                or len(value) > 256
                or any(ord(c) < 32 for c in value)
            ):
                raise ValueError("only non-secret bounded parsing headers are allowed")
        non_secret_json(self.body_json)
        if self.kind == "json_list" and (
            not self.title_paths or not (self.url_template or self.url_template_fallback)
        ):
            raise ValueError("JSON mapping needs title paths and a URL template")
        if self.kind == "json_list" and self.mode == "html_window_var" and not self.window_var:
            raise ValueError("window variable is required")
        if self.kind == "json_list" and self.mode == "html_json_key" and not self.json_key:
            raise ValueError("embedded JSON key is required")
        if self.kind == "x_search" and not self.query:
            raise ValueError("official X query is required")
        if self.kind == "mp_account" and not (self.ghid or self.wxid):
            raise ValueError("MP account identifier is required")
        for regex in [
            self.published_at_regex,
            self.detail.published_at_regex if self.detail else None,
            self.detail.title_regex if self.detail else None,
        ]:
            if regex:
                re.compile(regex)
                if re.search(r"\)[+*]|\\[1-9]|\(\?[=!<]", regex):
                    raise ValueError("source regex must use bounded capture rules")
        return self


class EditorialSourceMedia(EditorialContract):
    url: str = Field(max_length=2048)
    kind: Literal["image", "video", "audio", "unknown"] = "unknown"
    alt: str | None = Field(default=None, max_length=512)

    @field_validator("url")
    @classmethod
    def source_media_url(cls, value: str) -> str:
        return public_url(value)


class EditorialMaterial(EditorialContract):
    url: str = Field(max_length=2048)
    identity_key: str = Field(min_length=1, max_length=512)
    title: str = Field(min_length=1, max_length=2000)
    author: str | None = Field(default=None, max_length=256)
    language: str | None = Field(default=None, max_length=32)
    external_id: str | None = Field(default=None, max_length=512)
    native_identity: EditorialNativeIdentityProof | None = None
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    excerpt: str | None = Field(default=None, max_length=4000)
    body_text: str | None = Field(default=None, max_length=100_000)
    body_html: str | None = Field(default=None, max_length=500_000)
    body_markdown: str | None = Field(default=None, max_length=500_000)
    content_format: Literal["text", "html", "markdown"] = "text"
    body_status: Literal["ok", "pending", "none"] = "pending"
    media: tuple[str, ...] = Field(default=(), max_length=6)
    media_details: tuple[EditorialSourceMedia, ...] = Field(default=(), max_length=6)
    categories: tuple[str, ...] = Field(default=(), max_length=100)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return public_url(value, keep_fragment=True)

    @field_validator("published_at", "source_updated_at")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("source time must be timezone-aware")
        return value.astimezone(UTC) if value else None

    @model_validator(mode="after")
    def bounded_material(self) -> Self:
        non_secret_json(self.metadata)

        def check_metadata(node: JsonValue) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
                    if normalized in _MATERIAL_META_RESERVED:
                        raise ValueError("material and permission facts need their owning contract")
                    check_metadata(child)
            elif isinstance(node, list):
                for child in node:
                    check_metadata(child)

        check_metadata(self.metadata)
        if self.body_status == "ok" and not self.body_text:
            raise ValueError("complete body needs source text")
        if self.body_status == "ok" and (
            (self.content_format == "html" and not self.body_html)
            or (self.content_format == "markdown" and not self.body_markdown)
        ):
            raise ValueError("declared representation needs its matching source body")
        if any(len(word) > 128 for word in self.categories):
            raise ValueError("category exceeds limit")
        for url in self.media:
            public_url(url)
        if any(item.url not in self.media for item in self.media_details):
            raise ValueError("typed attachment must refer to an admitted media URL")
        return self


class RssValidator(EditorialContract):
    configuration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    response_url: str = Field(max_length=2048)
    etag: str | None = Field(default=None, max_length=512)
    last_modified: str | None = Field(default=None, max_length=512)


class SearchBacklog(EditorialContract):
    query: str = Field(min_length=1, max_length=1024)
    next_token: str = Field(min_length=1, max_length=4096)
    stop_at_id: str | None = Field(default=None, pattern=r"^[0-9]{1,19}$")
    state: Literal["pending", "held"] = "pending"
    failure_code: str | None = Field(default=None, max_length=64)
    group_manifest_json: str | None = Field(default=None, max_length=262_144)


class EditorialCursor(EditorialContract):
    initialized_at: datetime | None = None
    last_ok_at: datetime | None = None
    rss: RssValidator | None = None
    last_tweet_id: str | None = Field(default=None, pattern=r"^[0-9]{1,19}$")
    x_backlog: tuple[SearchBacklog, ...] = Field(default=(), max_length=100)
    last_checked_at: datetime | None = None
    last_post_time: datetime | None = None


class EditorialPage(EditorialContract):
    status: Literal["complete", "unchanged", "partial", "blocked", "unknown"]
    materials: tuple[EditorialMaterial, ...] = Field(default=(), max_length=1000)
    filtered: int = Field(default=0, ge=0, le=1000)
    cursor: EditorialCursor = EditorialCursor()
    reason: str | None = Field(default=None, max_length=64)
    request_count: int = Field(default=0, ge=0, le=100)
    observed_at: datetime


class EditorialBodyTarget(EditorialContract):
    owner_id: UUID
    run_id: UUID
    profile_id: UUID
    configuration_version: int
    profile_revision: int
    job_id: UUID
    operation_id: UUID
    content_id: UUID
    expected_content_version_id: UUID
    feed_observation_id: UUID
    material: EditorialMaterial

    @property
    def target_url(self) -> str:
        return self.material.url


class EditorialBodyCheckpoint(EditorialContract):
    targets: tuple[EditorialBodyTarget, ...] = Field(default=(), max_length=20)
    next_index: int = Field(default=0, ge=0, le=20)
    request_pending: bool = False
    completed_observation_ids: tuple[UUID, ...] = Field(default=(), max_length=20)
    failure_codes: tuple[str, ...] = Field(default=(), max_length=21)
    local_collector_calls: int = Field(default=0, ge=0, le=20)
    target_request_count: None = None


class EditorialAuthorization(EditorialContract):
    connection_enabled: bool = False
    owner_authorized: bool = False
    budget_confirmed: bool = False
    credentials_ready: bool = False

    @property
    def allowed(self) -> bool:
        return all(
            (
                self.connection_enabled,
                self.owner_authorized,
                self.budget_confirmed,
                self.credentials_ready,
            )
        )


class EditorialProfileView(EditorialContract):
    id: UUID
    source_key: str
    name: str
    enabled: bool
    revision: int
    configuration_version: int
    configuration_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    configuration: EditorialSourceConfiguration
    participation_mode: ParticipationMode
    tier: Literal["T1", "T1_5", "T2", "T3"]
    first_party: bool
    connection_id: UUID | None
    connection_version: int | None
    policy_version: int
    interval_minutes: int
    health: Literal["unknown", "ok", "degraded", "failing"]
    failure_count: int
    last_fetch_at: datetime | None
    last_ok_at: datetime | None
    next_fetch_at: datetime | None
    has_backlog: bool
    has_unknown_run: bool = False


class EditorialDue(EditorialContract):
    owner_id: UUID
    profile_id: UUID
    source_key: str
    configuration_version: int
    revision: int
    due_at: datetime
    kind: EditorialSourceKind


class EditorialRunResult(EditorialContract):
    run_id: UUID
    status: Literal["running", "succeeded", "partial", "unknown", "failed", "blocked", "cancelled"]
    configuration_version: int
    found: int = Field(default=0, ge=0)
    filtered: int = Field(default=0, ge=0)
    created: int = Field(default=0, ge=0)
    revised: int = Field(default=0, ge=0)
    reason: str | None = Field(default=None, max_length=64)
