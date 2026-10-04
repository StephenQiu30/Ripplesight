"""Frozen local RSSHub declarations; declarations alone never authorize a request."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote, unquote, urlencode, urlsplit

from pydantic import Field, field_validator, model_validator

from sources.adapters.rsshub_endpoint import RSSHUB_HOSTS
from sources.adapters.web_targets import normalize_web_host
from sources.editorial_base import EditorialContract

RSSHUB_REVISION = "0a3a66a1cb28a645ffe90577a68411886274a2ee"


class EditorialRsshubReview(EditorialContract):
    """Non-secret review references, also frozen into the operator approval audit."""

    purpose_reference: str = Field(min_length=1, max_length=128)
    downstream_reference: str = Field(min_length=1, max_length=128)
    cache_reference: str = Field(min_length=1, max_length=128)
    fee_reference: str = Field(min_length=1, max_length=128)
    stop_reference: str = Field(min_length=1, max_length=128)
    deployment_reference: str = Field(min_length=1, max_length=128)
    reviewed_at: datetime
    expires_at: datetime

    @field_validator(
        "purpose_reference",
        "downstream_reference",
        "cache_reference",
        "fee_reference",
        "stop_reference",
        "deployment_reference",
    )
    @classmethod
    def safe_reference(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 for char in value) or "?" in value:
            raise ValueError("review reference must not contain query credentials or controls")
        return value

    @model_validator(mode="after")
    def bounded_review(self) -> EditorialRsshubReview:
        if not 0 < (self.expires_at - self.reviewed_at).total_seconds() <= 90 * 86400:
            raise ValueError("RSSHub review must expire within 90 days")
        return self


class EditorialRsshubConfiguration(EditorialContract):
    platform: str = Field(pattern=r"^(x|instagram|facebook|threads|douyin|bilibili|weibo)$")
    query_mode: str = Field(pattern=r"^(author_stream|tag_feed|platform_keyword|hotlist)$")
    target: str = Field(min_length=1, max_length=256)
    route: str = Field(min_length=2, max_length=1024)
    query_parameters: dict[str, str] = Field(default_factory=dict, max_length=1)
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    item_hosts: tuple[str, ...] = Field(min_length=1, max_length=8)
    downstream_hosts: tuple[str, ...] = Field(min_length=1, max_length=16)
    text_scope: str = Field(pattern=r"^(post_text|caption|video_description|excerpt)$")
    credential_mode: str = Field(default="anonymous", pattern=r"^(anonymous|fixed_cookie)$")
    supplier_fee_cny_micros: int = Field(default=0, ge=0, le=0)
    fallback: str = Field(default="none", pattern=r"^none$")
    browser: str = Field(default="disabled", pattern=r"^disabled$")
    max_local_requests: int = Field(default=1, ge=1, le=1)
    max_downstream_requests: int = Field(ge=1, le=50)
    max_items: int = Field(default=30, ge=1, le=200)
    max_response_bytes: int = Field(default=1_048_576, ge=1024, le=4_194_304)
    max_seconds: int = Field(default=30, ge=1, le=90)
    cache_ttl_seconds: int = Field(ge=0, le=86_400)
    min_interval_minutes: int = Field(default=60, ge=1, le=360)
    review: EditorialRsshubReview

    @field_validator("route")
    @classmethod
    def safe_route(cls, value: str) -> str:
        parts = urlsplit(value)
        decoded = unquote(value)
        if (
            parts.scheme
            or parts.netloc
            or parts.query
            or parts.fragment
            or not value.startswith("/")
            or value.startswith("//")
            or "\\" in decoded
            or any(ord(char) < 32 for char in decoded)
            or any(part in {".", "..", ""} for part in decoded.split("/")[1:])
            or re.search(r"%(?:2f|5c|25)", value, re.IGNORECASE)
        ):
            raise ValueError("RSSHub route must be one frozen path without traversal")
        return value

    @field_validator("item_hosts", "downstream_hosts")
    @classmethod
    def exact_public_hosts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted(normalize_web_host(host) for host in value))
        if len(set(normalized)) != len(normalized):
            raise ValueError("RSSHub hosts must be unique exact public hosts")
        return normalized

    @model_validator(mode="after")
    def frozen_parameters(self) -> EditorialRsshubConfiguration:
        if set(self.query_parameters) - {"limit"}:
            raise ValueError("only the bounded RSSHub output limit parameter is supported")
        if self.query_parameters and self.query_parameters != {"limit": str(self.max_items)}:
            raise ValueError("RSSHub output limit must equal the frozen item bound")
        if any(ord(char) < 32 for char in self.target):
            raise ValueError("RSSHub target contains controls")
        return self

    def endpoint(self, host: str) -> str:
        if host not in RSSHUB_HOSTS:
            raise ValueError("RSSHub host must be a fixed local service")
        query = urlencode(sorted(self.query_parameters.items()))
        return f"http://{host}:1200{self.route}" + (f"?{query}" if query else "")


@dataclass(frozen=True, slots=True)
class EditorialRsshubAdmission:
    configuration_sha256: str
    revision: str
    reviewed_at: datetime
    expires_at: datetime
    max_downstream_requests: int
    supplier_fee_cny_micros: int = 0
    # A frozen upper bound is not telemetry: source-side request count remains unknown.
    downstream_request_count: None = None


def rsshub_route_blocker(config: EditorialRsshubConfiguration) -> str | None:
    """Installed candidates remain blocked unless this exact safe branch is reviewed.

    The deployment review must establish the underlying service's egress, retry,
    cookie and cache configuration. This function does not inspect or certify it.
    """
    if config.revision != RSSHUB_REVISION:
        return "rsshub_revision_unapproved"
    target = quote(config.target, safe="")
    if config.platform == "threads":
        if config.credential_mode != "anonymous" or config.text_scope != "post_text":
            return "rsshub_route_unapproved"
        hosts = {"www.threads.com"}
        expected = (
            {f"/threads/{target}"}
            if config.query_mode == "author_stream"
            else {
                f"/threads/search/{target}",
                f"/threads/search/{target}/serpType=tags",
                f"/threads/search/{target}/serpType=default",
                f"/threads/search/{target}/serpType=recent",
            }
            if config.query_mode in {"platform_keyword", "tag_feed"}
            else set()
        )
        if config.query_mode == "platform_keyword":
            expected -= {f"/threads/search/{target}", f"/threads/search/{target}/serpType=tags"}
        if config.query_mode == "tag_feed":
            expected &= {f"/threads/search/{target}", f"/threads/search/{target}/serpType=tags"}
        if config.route not in expected:
            return "rsshub_query_contract_mismatch"
        if set(config.item_hosts) != hosts or set(config.downstream_hosts) != hosts:
            return "rsshub_downstream_unapproved"
        if config.max_downstream_requests < 1:
            return "rsshub_downstream_unapproved"
        return None
    if config.platform == "instagram":
        if (
            config.route != f"/instagram/2/user/{target}"
            or config.query_mode != "author_stream"
            or config.credential_mode != "anonymous"
            or config.text_scope != "caption"
        ):
            return "rsshub_route_unapproved"
        if set(config.item_hosts) != {"www.instagram.com"} or set(config.downstream_hosts) != {
            "www.instagram.com"
        }:
            return "rsshub_downstream_unapproved"
        return None
    # Cookie lifecycle, browser fallback or secrets/fees cannot be disabled by
    # a caller's metadata. Those installed candidates have no executable contract.
    return {
        "x": "rsshub_x_secret_and_fee_boundary",
        "facebook": "rsshub_facebook_route_unavailable",
        "douyin": "rsshub_browser_route_blocked",
        "weibo": "rsshub_fixed_cookie_branch_unverified",
        "bilibili": "rsshub_bilibili_route_unverified",
    }.get(config.platform, "rsshub_route_unapproved")
