"""Server-admitted local Firecrawl body reads; no implicit proof or resource grant."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from sources.adapters.firecrawl import FirecrawlAdapter
from sources.adapters.web_targets import normalize_web_url
from sources.contracts import SourceStopReason, WebPageRequest, WebPageResult
from sources.editorial_schemas import EditorialBodyConfiguration, EditorialBodyTarget


@dataclass(frozen=True, slots=True)
class EditorialBodyAdmission:
    profile_id: UUID
    configuration_version: int
    profile_revision: int
    configuration_sha256: str
    proof_reference: str
    component_version: str
    reviewed_at: datetime
    expires_at: datetime
    allowed_hosts: frozenset[str]
    read_allowed: bool
    save_allowed: bool
    zero_supplier_fee_verified: bool
    target_egress_verified: bool


type BodyAdmission = Callable[[EditorialBodyTarget], EditorialBodyAdmission | None]
type BodyBeforeRequest = Callable[[EditorialBodyTarget], bool]
type BodySettle = Callable[[EditorialBodyTarget, WebPageResult], None]


class LocalEditorialBodyFetcher:
    def __init__(
        self,
        *,
        base_url: str,
        configuration_sha256: str,
        admission: BodyAdmission | None = None,
        before_request: BodyBeforeRequest | None = None,
        settle: BodySettle | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "host.docker.internal"}
            or parsed.port != 3002
            or parsed.path not in {"", "/"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("body extraction requires the fixed local Firecrawl endpoint")
        self._url, self._hash = base_url, configuration_sha256
        self._admit, self._before, self._settle = admission, before_request, settle
        self._transport, self._clock = transport, clock

    def fetch(
        self, target: EditorialBodyTarget, configuration: EditorialBodyConfiguration
    ) -> WebPageResult:
        if (
            not configuration.enabled
            or configuration.review is None
            or self._admit is None
            or self._before is None
            or self._settle is None
        ):
            return self._denied()
        proof = self._admit(target)
        now = self._clock()
        if (
            proof is None
            or now.utcoffset() is None
            or proof.reviewed_at.utcoffset() is None
            or proof.expires_at.utcoffset() is None
            or not proof.reviewed_at <= now < proof.expires_at
            or proof.profile_id != target.profile_id
            or proof.configuration_version != target.configuration_version
            or proof.profile_revision != target.profile_revision
            or proof.configuration_sha256 != self._hash
            or proof.reviewed_at != configuration.review.reviewed_at
            or proof.expires_at != configuration.review.expires_at
            or not proof.proof_reference.strip()
            or not proof.component_version.strip()
            or not all(
                (
                    proof.read_allowed,
                    proof.save_allowed,
                    proof.zero_supplier_fee_verified,
                    proof.target_egress_verified,
                )
            )
        ):
            return self._denied()
        allowed_hosts = frozenset(configuration.allowed_hosts) & proof.allowed_hosts
        try:
            normalize_web_url(target.target_url, allowed_hosts=allowed_hosts)
        except ValueError:
            return self._denied()
        if not self._before(target):
            return self._denied(SourceStopReason.BUDGET_EXHAUSTED)
        with FirecrawlAdapter(
            base_url=self._url,
            enabled=True,
            allowed_hosts=allowed_hosts,
            max_response_bytes=configuration.max_response_bytes,
            transport=self._transport,
            clock=self._clock,
        ) as adapter:
            result = adapter.fetch_document(
                WebPageRequest(
                    url=target.target_url,
                    timeout_seconds=configuration.timeout_seconds,
                    max_content_characters=configuration.max_content_characters,
                )
            )
        self._settle(target, result)
        return result

    @staticmethod
    def _denied(reason: SourceStopReason = SourceStopReason.ACCESS_DENIED) -> WebPageResult:
        return WebPageResult(
            document=None,
            stop_reason=reason,
            target_status_code=None,
            collector_call_count=0,
            target_request_count=None,
        )
