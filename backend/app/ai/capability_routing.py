"""Create the exact frozen model from the protected server catalog."""

import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import httpx

from ai.adapters.codex_app_server import CodexAppServerClient
from ai.adapters.openai_compatible import OpenAiCompatibleClient
from ai.capability_schemas import FrozenAiModel
from ai.capability_services import protected_model_catalog
from ai.schemas import AiCallError, AiFailureCode
from core.config import Settings


def create_ai_client_for_frozen_model(
    settings: Settings,
    model: FrozenAiModel,
    *,
    transport: httpx.BaseTransport | None = None,
    before_request: Callable[[], None] | None = None,
) -> CodexAppServerClient | OpenAiCompatibleClient:
    spec = protected_model_catalog(settings).get(model.key)
    if (
        spec is None
        or not settings.ai_enabled
        or spec.sha256 != model.catalog_sha256
        or spec.model != model.model
        or spec.provider_key != model.provider
        or spec.component_key != model.component_key
        or spec.vision != model.vision
    ):
        raise AiCallError(AiFailureCode.UNAVAILABLE, "frozen model catalog is no longer approved")
    client: Any
    reasoning_config = (
        "HOTKEY_AI_REASONING_TOKENS"
        if model.key == "default"
        and "reasoning_tokens" not in settings.ai_model_catalog.get("default", {})
        else f"HOTKEY_AI_MODEL_CATALOG.{model.key}.reasoning_tokens"
    )
    if spec.transport == "codex":
        command = shlex.split(settings.ai_command)
        if len(command) != 2 or Path(command[0]).name != "codex" or command[1] != "app-server":
            raise AiCallError(AiFailureCode.UNAVAILABLE, "analysis command is not Codex app-server")
        client = CodexAppServerClient(
            model=spec.model,
            command=command,
            effort=settings.ai_effort,
            timeout_seconds=spec.timeout_seconds,
            reasoning_tokens=spec.reasoning_tokens,
            reasoning_config=reasoning_config,
        )
    else:
        if not settings.ai_openai_compatible_requests_enabled or not spec.configured:
            raise AiCallError(AiFailureCode.UNAVAILABLE, "compatible provider is disabled")
        if spec.currency is None:
            raise AiCallError(AiFailureCode.UNAVAILABLE, "compatible model price is not reviewed")
        if (
            spec.quote(input_tokens_cap=1, output_tokens_cap=1).cap_micros > 0
            and not settings.ai_paid_requests_enabled
        ):
            raise AiCallError(AiFailureCode.UNAVAILABLE, "paid model requests are disabled")
        client = OpenAiCompatibleClient(
            spec,
            enabled=True,
            transport=transport,
            before_request=before_request,
            reasoning_config=reasoning_config,
        )
    client.component_key = spec.component_key
    client.capability_settings = settings
    client.frozen_model = model
    client.pricing_spec = spec if spec.currency is not None else None
    return cast(CodexAppServerClient | OpenAiCompatibleClient, client)
