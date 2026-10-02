"""Protected server model catalog and eleven capability contracts, without public credentials."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from typing import Any, Literal, Self, cast
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from operations.schemas import OperatorAuditView

CapabilityKey = Literal[
    "prefilter",
    "score",
    "understand",
    "summarize",
    "structure",
    "group",
    "groupReview",
    "digest",
    "report",
    "translate",
    "monitor",
]


@dataclass(frozen=True)
class CapabilityDefinition:
    label: str
    env: str
    purposes: tuple[str, ...]


AI_CAPABILITIES: dict[CapabilityKey, CapabilityDefinition] = {
    "prefilter": CapabilityDefinition("精选预筛", "PREFILTER_MODEL", ("prefilter_article",)),
    "score": CapabilityDefinition("精选评分", "SCORE_MODEL", ("score_article",)),
    "understand": CapabilityDefinition("内容理解", "UNDERSTAND_MODEL", ("understand_article",)),
    "summarize": CapabilityDefinition("标题摘要", "SUMMARIZE_MODEL", ("summarize_article",)),
    "structure": CapabilityDefinition("结构抽取", "STRUCTURE_MODEL", ("structure_article",)),
    "group": CapabilityDefinition(
        "事件归组", "GROUP_MODEL", ("group_article", "group_signal", "group_story")
    ),
    "groupReview": CapabilityDefinition(
        "归组复核", "GROUP_REVIEW_MODEL", ("group_review", "group_story_review")
    ),
    "digest": CapabilityDefinition("事件综述", "DIGEST_MODEL", ("story_digest",)),
    "report": CapabilityDefinition(
        "日报周报月报",
        "REPORT_MODEL",
        ("report_lead", "report_daily", "report_weekly", "report_monthly"),
    ),
    "translate": CapabilityDefinition(
        "精选全文翻译", "TRANSLATE_MODEL", ("translate_body", "translate_quoted")
    ),
    "monitor": CapabilityDefinition(
        "Codex重置公告", "MONITOR_MODEL", ("monitor.recognize", "monitor.context")
    ),
}


def capability_for_purpose(purpose: str) -> CapabilityKey:
    for key, definition in AI_CAPABILITIES.items():
        if purpose in definition.purposes:
            return key
    name = purpose.removeprefix("analysis.selectbench.").removeprefix("editorial.")
    if name in {"score_1", "score_2", "score-1", "score-2", "score", "score1", "score2"}:
        return "score"
    if name in {"prefilter", "understand", "summarize", "structure"}:
        return cast(CapabilityKey, name)
    if purpose == "analysis.selectbench.relation-pair":
        return "group"
    if purpose in {"editorial.translation", "publication.translate"}:
        return "translate"
    if purpose.startswith("monitor."):
        return "monitor"
    if "review" in purpose and purpose.startswith(("events.", "story.")):
        return "groupReview"
    if purpose in {"events.digest", "story.digest"}:
        return "digest"
    if purpose.startswith("report."):
        return "report"
    if purpose in {
        "events.cluster",
        "events.signal-relation",
        "story.group",
    } or purpose.startswith("events.consolidate."):
        return "group"
    if purpose == "analysis.annotate":
        return "understand"
    raise ValueError("AI purpose has no registered capability")


class AiCapabilityContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class AiPriceQuote(AiCapabilityContract):
    currency: Literal["USD", "CNY"]
    input_tokens_cap: int = Field(ge=0, le=16_000_000)
    output_tokens_cap: int = Field(ge=1, le=32768)
    input_rate_micros_per_million: Decimal = Field(ge=0, le=Decimal("1000000000000"))
    output_rate_micros_per_million: Decimal = Field(ge=0, le=Decimal("1000000000000"))
    cached_input_rate_micros_per_million: Decimal | None = Field(default=None, ge=0)

    @property
    def cap_micros(self) -> int:
        rate = max(
            self.input_rate_micros_per_million,
            self.cached_input_rate_micros_per_million or Decimal(0),
        )
        amount = (
            self.input_tokens_cap * rate
            + self.output_tokens_cap * self.output_rate_micros_per_million
        ) / 1_000_000
        return int(amount.to_integral_value(rounding=ROUND_CEILING))

    def estimate(self, input_tokens: int, cached_tokens: int, output_tokens: int) -> int:
        if min(input_tokens, cached_tokens, output_tokens) < 0 or cached_tokens > input_tokens:
            raise ValueError("model token usage is invalid")
        cached_rate = self.cached_input_rate_micros_per_million
        amount = (
            (input_tokens - cached_tokens) * self.input_rate_micros_per_million
            + cached_tokens
            * (cached_rate if cached_rate is not None else self.input_rate_micros_per_million)
            + output_tokens * self.output_rate_micros_per_million
        ) / 1_000_000
        return int(amount.to_integral_value(rounding=ROUND_CEILING))


class AiModelServerSpec(AiCapabilityContract):
    transport: Literal["codex", "openai_compatible"]
    provider_key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,31}$")
    model: str = Field(min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=2048, exclude=True, repr=False)
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    vision: bool = False
    text_compatible: bool = True
    json_mode: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)
    currency: Literal["USD", "CNY"] | None = None
    input_rate_micros_per_million: Decimal | None = Field(default=None, ge=0)
    output_rate_micros_per_million: Decimal | None = Field(default=None, ge=0)
    cached_input_rate_micros_per_million: Decimal | None = Field(default=None, ge=0)
    max_output_tokens: int = Field(default=4096, ge=512, le=32768)
    timeout_seconds: int = Field(default=120, ge=1, le=600)

    @model_validator(mode="after")
    def protected_spec(self) -> Self:
        if not self.text_compatible:
            raise ValueError("registered editorial capabilities require text compatibility")
        if self.transport == "codex" and self.provider_key != "codex_app_server":
            raise ValueError("Codex requires its actual provider identity")
        if self.base_url is not None:
            u = urlsplit(self.base_url)
            if (
                u.scheme != "https"
                or not u.hostname
                or u.username
                or u.password
                or u.query
                or u.fragment
            ):
                raise ValueError(
                    "compatible model base URL needs explicit HTTPS without credentials"
                )
        if len(json.dumps(self.extra, ensure_ascii=False, allow_nan=False).encode()) > 4096:
            raise ValueError("model extra parameters exceed the bounded catalog")
        for name in self.extra:
            if name.lower() in {
                "model",
                "messages",
                "headers",
                "authorization",
                "api_key",
                "max_tokens",
                "max_completion_tokens",
                "stream",
                "tools",
                "tool_choice",
                "response_format",
            }:
                raise ValueError("model extra parameters cannot replace request authority")
        rates = (self.input_rate_micros_per_million, self.output_rate_micros_per_million)
        if self.currency is None and any(rate is not None for rate in rates):
            raise ValueError("model price must declare its original currency")
        if self.currency is not None and any(rate is None for rate in rates):
            raise ValueError("model currency requires both conservative token rates")
        return self

    @property
    def component_key(self) -> str:
        return "codex.app-server" if self.transport == "codex" else f"ai.llm.{self.provider_key}"

    @property
    def configured(self) -> bool:
        return self.transport == "codex" or bool(self.base_url and self.api_key)

    @property
    def sha256(self) -> str:
        payload = {**self.model_dump(mode="json"), "endpoint": self.base_url}
        return digest(payload)

    def quote(self, *, input_tokens_cap: int, output_tokens_cap: int) -> AiPriceQuote:
        if self.currency is None:
            raise ValueError("model price is unknown")
        return AiPriceQuote(
            currency=self.currency,
            input_tokens_cap=input_tokens_cap,
            output_tokens_cap=output_tokens_cap,
            input_rate_micros_per_million=self.input_rate_micros_per_million,
            output_rate_micros_per_million=self.output_rate_micros_per_million,
            cached_input_rate_micros_per_million=self.cached_input_rate_micros_per_million,
        )


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


class FrozenAiModel(AiCapabilityContract):
    key: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    provider: str = Field(max_length=64)
    model: str = Field(min_length=1, max_length=128)
    component_key: str = Field(max_length=64)
    vision: bool
    catalog_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class FrozenAiRouting(AiCapabilityContract):
    owner_id: UUID
    configuration_version: int = Field(ge=0)
    models: dict[CapabilityKey, FrozenAiModel]

    @model_validator(mode="after")
    def complete_map(self) -> Self:
        if set(self.models) != set(AI_CAPABILITIES):
            raise ValueError("frozen AI routing must cover all eleven capabilities")
        if len(self.model_dump_json().encode()) > 65536:
            raise ValueError("frozen AI routing exceeds the original Job scope bound")
        return self

    @property
    def sha256(self) -> str:
        return digest(self.model_dump(mode="json"))

    def for_purpose(self, purpose: str) -> FrozenAiModel:
        return self.models[capability_for_purpose(purpose)]


class AiModelSwitchInput(AiCapabilityContract):
    operation_id: UUID
    expected_version: int = Field(ge=0)
    capability: CapabilityKey
    model_key: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    reason: str = Field(min_length=1, max_length=1000)
    actor: str = Field(default="Workspace operator", min_length=1, max_length=128)


class FrozenAiBenchmark(AiCapabilityContract):
    owner_id: UUID
    configuration_version: int = Field(ge=0)
    models: dict[str, FrozenAiModel] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def bounded_snapshot(self) -> Self:
        if (
            any(not key or len(key) > 64 for key in self.models)
            or len(self.model_dump_json().encode()) > 65536
        ):
            raise ValueError("benchmark frozen models exceed their protected bound")
        return self

    @property
    def sha256(self) -> str:
        return digest(self.model_dump(mode="json"))


class AiModelChoice(AiCapabilityContract):
    key: str
    provider: str
    model: str
    vision: bool
    configured: bool
    component_key: str
    currency: Literal["USD", "CNY"] | None
    input_rate_micros_per_million: Decimal | None
    output_rate_micros_per_million: Decimal | None


class AiCostCircuitAckInput(AiCapabilityContract):
    operation_id: UUID
    expected_version: int = Field(ge=0)
    call_id: UUID
    reason: str = Field(min_length=1, max_length=1000)


class AiCostCircuitView(AiCapabilityContract):
    call_id: UUID
    provider: str
    model: str
    currency: Literal["USD", "CNY"]
    cost_actual_micros: int
    cost_cap_micros: int
    acknowledged: bool
    created_at: datetime


class AiCapabilityChoice(AiCapabilityContract):
    key: CapabilityKey
    label: str
    env: str
    default_model: str = "default"
    current: FrozenAiModel
    source: Literal["admin", "env", "default"]


class AiModelConfigurationView(AiCapabilityContract):
    version: int = Field(ge=0)
    created_at: datetime | None
    capabilities: tuple[AiCapabilityChoice, ...]
    choices: tuple[AiModelChoice, ...]
    calls_enabled: bool
    paid_requests_enabled: bool
    compatible_requests_enabled: bool


class AiModelUsageView(AiCapabilityContract):
    capability: CapabilityKey | Literal["embedding"]
    purpose: str
    provider: str
    model: str
    prompt_version: str
    calls: int
    succeeded: int
    failed: int
    unknown: int
    running: int = 0
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    currency: str | None
    cost_estimate_micros: int | None
    cost_actual_micros: int | None
    cost_cap_micros: int | None


class AiModelOverview(AiCapabilityContract):
    days: int = Field(ge=1, le=90)
    configuration: AiModelConfigurationView
    usage: tuple[AiModelUsageView, ...]
    history: tuple[OperatorAuditView, ...]
    cost_circuits: tuple[AiCostCircuitView, ...] = ()
