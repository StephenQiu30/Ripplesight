from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from ai.adapters.openai_compatible import OpenAiCompatibleClient
from ai.capability_routing import create_ai_client_for_frozen_model
from ai.capability_schemas import AiModelServerSpec, FrozenAiModel
from ai.capability_services import _configuration, protected_model_catalog
from ai.models import AiCall
from ai.schemas import AiCallError, AiCallStatus, AiFailureCode
from ai.services import AiService
from core.config import Settings


def test_ai_failure_enum_is_accepted_by_canonical_ddl_and_runtime_constraint():
    codes = {code.value for code in AiFailureCode}
    ddl = (Path(__file__).resolve().parents[2] / "database" / "schema.sql").read_text()
    ai_table = ddl.split("CREATE TABLE ai_calls (", 1)[1].split("CREATE TABLE", 1)[0]
    allowed = re.search(r"failure_code IN \(([^)]+)\)", ai_table)
    assert allowed is not None
    assert set(re.findall(r"'([a-z_]+)'", allowed.group(1))) == codes
    constraint = next(
        constraint
        for constraint in AiCall.__table__.constraints
        if constraint.name == "ai_calls_failure_code_check"
    )
    assert set(re.findall(r"'([a-z_]+)'", str(constraint.sqltext))) == codes


def _settings(**overrides):
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://controlled@127.0.0.1/hotkey_test_reasoning",
        **overrides,
    )


def _spec(**overrides):
    return AiModelServerSpec(
        **{
            "transport": "openai_compatible",
            "provider_key": "controlled",
            "model": "ordinary-name",
            "base_url": "https://models.example/v1",
            "api_key": "private-provider-secret",
            "currency": "USD",
            "input_rate_micros_per_million": Decimal("1000000"),
            "output_rate_micros_per_million": Decimal("2000000"),
            **overrides,
        }
    )


@pytest.mark.parametrize("value", ["0", "4000", "28672"])
def test_default_reasoning_tokens_parse_explicit_environment(monkeypatch, value):
    monkeypatch.setenv("HOTKEY_AI_REASONING_TOKENS", value)
    settings = _settings()
    assert settings.ai_reasoning_tokens == int(value)
    assert protected_model_catalog(settings)["default"].reasoning_tokens == int(value)
    assert not settings.ai_enabled


@pytest.mark.parametrize("value", ["-1", "+1", "1.5", "secret-input", "28673", True, 1.5])
def test_reasoning_tokens_reject_non_integer_or_unbounded_values(value):
    with pytest.raises(ValidationError):
        _settings(ai_reasoning_tokens=value)
    with pytest.raises(ValidationError):
        _spec(reasoning_tokens=value)


def test_reasoning_configuration_defaults_overrides_zero_and_no_model_name_inference(monkeypatch):
    monkeypatch.delenv("HOTKEY_AI_REASONING_TOKENS", raising=False)
    assert _settings().ai_reasoning_tokens == 0
    assert _spec(model="name-think", reasoning_tokens=0).reasoning_tokens == 0
    named = _spec(reasoning_tokens=4000).model_dump()
    default = {**named, "reasoning_tokens": 0}
    settings = _settings(
        ai_reasoning_tokens=2000,
        ai_model_catalog={"default": default, "named": named, "plain-think": _spec().model_dump()},
        ai_capability_models={"score": "named"},
    )
    catalog = protected_model_catalog(settings)
    assert catalog["default"].reasoning_tokens == 0
    assert catalog["named"].reasoning_tokens == 4000
    assert catalog["plain-think"].reasoning_tokens == 0
    # Admin choice > capability environment choice > default, including an explicit zero.
    session = Mock()
    session.scalar.return_value = None
    env_view = _configuration(session, owner_id=uuid4(), settings=settings)
    assert next(c for c in env_view.capabilities if c.key == "score").current.key == "named"
    assert next(c for c in env_view.capabilities if c.key == "structure").current.key == "default"
    session.scalar.return_value = SimpleNamespace(
        overrides={"score": "plain-think"}, version=1, created_at=datetime.now(UTC)
    )
    admin_view = _configuration(session, owner_id=uuid4(), settings=settings)
    assert next(c for c in admin_view.capabilities if c.key == "score").current.key == "plain-think"
    inherited = {key: value for key, value in default.items() if key != "reasoning_tokens"}
    settings = _settings(ai_reasoning_tokens=2000, ai_model_catalog={"default": inherited})
    assert protected_model_catalog(settings)["default"].reasoning_tokens == 2000


def test_reasoning_limit_is_bounded_and_changes_frozen_catalog_hash():
    spec = _spec(max_output_tokens=512, reasoning_tokens=32256)
    assert spec.output_tokens_limit == 32768
    with pytest.raises(ValidationError):
        _spec(max_output_tokens=4096, reasoning_tokens=28673)
    assert _spec().sha256 != _spec(reasoning_tokens=1).sha256
    assert "private-provider-secret" not in _spec(reasoning_tokens=4000).model_dump_json()
    with pytest.raises(ValidationError):
        _settings(
            ai_reasoning_tokens=2000,
            ai_model_catalog={
                "default": {
                    **_spec().model_dump(),
                    "max_output_tokens": 32768,
                    "reasoning_tokens": 1,
                }
            },
        )


@pytest.mark.parametrize(
    "model_key,override", [("default", False), ("default", True), ("named", True)]
)
def test_routed_client_uses_exact_allowance_and_configuration_hint(model_key, override):
    raw = _spec().model_dump()
    raw.update(base_url="https://models.example/v1", api_key="private-provider-secret")
    if override:
        raw["reasoning_tokens"] = 4000
    else:
        del raw["reasoning_tokens"]
    settings = _settings(
        ai_enabled=True,
        ai_openai_compatible_requests_enabled=True,
        ai_paid_requests_enabled=True,
        ai_reasoning_tokens=2000,
        ai_model_catalog={model_key: raw},
    )
    spec = protected_model_catalog(settings)[model_key]
    frozen = FrozenAiModel(
        key=model_key,
        provider=spec.provider_key,
        model=spec.model,
        component_key=spec.component_key,
        vision=spec.vision,
        catalog_sha256=spec.sha256,
    )
    client = create_ai_client_for_frozen_model(
        settings, frozen, transport=httpx.MockTransport(lambda request: httpx.Response(200))
    )
    try:
        assert client.spec.reasoning_tokens == (4000 if override else 2000)
        assert client.reasoning_config == (
            f"HOTKEY_AI_MODEL_CATALOG.{model_key}.reasoning_tokens"
            if override
            else "HOTKEY_AI_REASONING_TOKENS"
        )
    finally:
        client.close()
    changed = settings.model_copy(
        update={"ai_model_catalog": {model_key: {**raw, "reasoning_tokens": 1}}}
    )
    with pytest.raises(AiCallError) as caught:
        create_ai_client_for_frozen_model(changed, frozen)
    assert caught.value.code is AiFailureCode.UNAVAILABLE


@pytest.mark.parametrize("reasoning_tokens", [0, 4000])
def test_output_allowance_is_added_to_request_and_price_cap(reasoning_tokens):
    requests = []
    spec = _spec(max_output_tokens=512, reasoning_tokens=reasoning_tokens)

    def reply(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = OpenAiCompatibleClient(spec, enabled=True, transport=httpx.MockTransport(reply))
    try:
        assert client.complete(prompt="private source material", output_schema={}).output == {}
    finally:
        client.close()
    assert requests[0]["max_tokens"] == 512 + reasoning_tokens
    assert spec.quote(
        input_tokens_cap=100, output_tokens_cap=spec.output_tokens_limit
    ).cap_micros == (100 + 2 * (512 + reasoning_tokens))


@pytest.mark.parametrize("answer", ["", None, '{"cut', '{"valid":true}'])
@pytest.mark.parametrize(
    "usage",
    [
        None,
        {"prompt_tokens": "bad"},
        {
            "prompt_tokens": 100,
            "completion_tokens": 4512,
            "completion_tokens_details": {"reasoning_tokens": 4000},
        },
    ],
)
def test_length_is_a_stable_sanitized_error_even_for_valid_json_and_never_retries(answer, usage):
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "length", "message": {"content": answer}}],
                "usage": usage,
                "provider_debug": "private-provider-secret private source material",
            },
        )

    client = OpenAiCompatibleClient(
        _spec(reasoning_tokens=4000),
        enabled=True,
        transport=httpx.MockTransport(reply),
        reasoning_config="HOTKEY_AI_MODEL_CATALOG.named.reasoning_tokens",
    )
    try:
        with pytest.raises(AiCallError) as caught:
            client.complete(prompt="private source material", output_schema={})
    finally:
        client.close()
    error = caught.value
    assert error.code is AiFailureCode.OUTPUT_TRUNCATED
    assert "HOTKEY_AI_MODEL_CATALOG.named.reasoning_tokens" in error.detail
    assert len(requests) == 1
    safe = str(error) + error.detail + (error.receipt.model_dump_json() if error.receipt else "")
    assert "private-provider-secret" not in safe and "private source material" not in safe
    if isinstance(usage, dict) and isinstance(usage.get("completion_tokens"), int):
        assert error.receipt.output == {}
        assert error.receipt.usage.output_tokens == 4512
        assert error.receipt.usage.reasoning_output_tokens == 4000


def test_service_reserves_total_output_and_finishes_truncated_receipt_without_retry(monkeypatch):
    spec = _spec(max_output_tokens=512, reasoning_tokens=4000)
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "length", "message": {"content": "private source material"}}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 4512},
            },
        )

    client = OpenAiCompatibleClient(spec, enabled=True, transport=httpx.MockTransport(reply))
    client.pricing_spec = spec
    service = object.__new__(AiService)
    service._settings = _settings(ai_enabled=True, ai_paid_requests_enabled=True)
    service._clock = lambda: datetime.now(UTC)
    service._guard = lambda session: None
    service._epoch = 1
    monkeypatch.setattr(
        service,
        "_route",
        lambda *args: (client, SimpleNamespace(), SimpleNamespace(sha256="a" * 64), False),
    )
    reserve, finish = Mock(), Mock()
    monkeypatch.setattr(service, "_reserve", reserve)
    monkeypatch.setattr(service, "_finish", finish)
    try:
        with pytest.raises(AiCallError) as caught:
            service.complete(
                owner_id=uuid4(),
                job_id=uuid4(),
                purpose="editorial.understand",
                prompt_version="controlled",
                prompt="private source material",
                output_schema={},
            )
    finally:
        client.close()
    assert reserve.call_args.kwargs["quote"].output_tokens_cap == 4512
    assert len(requests) == reserve.call_count == finish.call_count == 1
    assert finish.call_args.kwargs["failure"] is AiFailureCode.OUTPUT_TRUNCATED
    assert finish.call_args.kwargs["status"] is AiCallStatus.UNKNOWN
    assert finish.call_args.kwargs["completion"].usage.output_tokens == 4512
    assert caught.value.call_id is not None and caught.value.outcome_unknown
