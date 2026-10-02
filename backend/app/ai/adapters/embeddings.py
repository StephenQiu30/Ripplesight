from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

import httpx

from ai.embedding_contract import EmbeddingPricing, FrozenEmbeddingConfiguration
from ai.schemas import AiCallError, AiCompletion, AiFailureCode, AiTokenUsage
from core.config import Settings


def compatible_vector(value: object, dimensions: int = 0) -> bool:
    try:
        return (
            isinstance(value, list)
            and 1 <= len(value) <= 3072
            and (dimensions == 0 or len(value) == dimensions)
            and all(
                isinstance(item, (float, int))
                and not isinstance(item, bool)
                and math.isfinite(item)
                for item in value
            )
        )
    except (OverflowError, ValueError):
        return False


def cosine(first: Sequence[float], second: Sequence[float]) -> float:
    if (
        not first
        or len(first) != len(second)
        or any(not math.isfinite(value) for value in (*first, *second))
    ):
        return 0
    numerator = sum(a * b for a, b in zip(first, second, strict=True))
    denominator = math.sqrt(
        sum(value * value for value in first) * sum(value * value for value in second)
    )
    score = numerator / denominator if denominator else 0
    return score if math.isfinite(score) else 0


class EmbeddingClient:
    """A real /embeddings adapter, exposed through the existing AiCall accounting protocol."""

    component_key = "ai.embeddings"

    provider = "openai-compatible-embedding"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int,
        timeout_seconds: int,
        transport: httpx.BaseTransport | None = None,
        configuration: FrozenEmbeddingConfiguration | None = None,
    ):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or not api_key
            or not 0 < len(model) <= 128
            or not 0 <= dimensions <= 3072
            or not 1 <= timeout_seconds <= 60
        ):
            raise ValueError("invalid embedding configuration")
        self.model, self._dimensions = model, dimensions
        self.provider = parsed.hostname
        self.embedding_configuration = configuration
        if configuration is not None:
            if (
                configuration.endpoint != base_url.rstrip("/")
                or configuration.model != model
                or configuration.dimensions != dimensions
            ):
                raise ValueError("embedding adapter differs from its frozen configuration")
            self.pricing_spec = EmbeddingPricing(configuration)
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": "Bearer " + api_key},
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=transport,
        )

    def complete(
        self, *, prompt: str, output_schema: Mapping[str, Any], instructions: str = ""
    ) -> AiCompletion:
        if not prompt.strip() or len(prompt) > 2000 or instructions:
            raise ValueError("embedding accepts bounded material without instructions")
        payload: dict[str, object] = {
            "model": self.model,
            "input": [prompt],
            "encoding_format": "float",
        }
        if self._dimensions:
            payload["dimensions"] = self._dimensions
        start = time.monotonic()
        try:
            response = self._client.post("embeddings", json=payload)
        except httpx.TimeoutException:
            raise AiCallError(AiFailureCode.TIMEOUT) from None
        except httpx.TransportError:
            raise AiCallError(AiFailureCode.FAILED) from None
        if response.status_code != 200:
            raise AiCallError(
                AiFailureCode.RATE_LIMITED
                if response.status_code == 429
                else AiFailureCode.UNAVAILABLE
                if response.status_code >= 500
                else AiFailureCode.INVALID_OUTPUT
            )
        try:
            if len(response.content) > 2_000_000:
                raise ValueError("oversized embedding response")
            result = response.json()
            data = result["data"]
            if (
                not isinstance(data, list)
                or len(data) != 1
                or type(data[0].get("index")) is not int
                or data[0].get("index") != 0
                or not compatible_vector(data[0].get("embedding"), self._dimensions)
                or result.get("model") != self.model
            ):
                raise ValueError("invalid embedding coordinates or identity")
            usage = result.get("usage")
            reported = isinstance(usage, dict) and "prompt_tokens" in usage
            tokens = usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0
            if (
                isinstance(tokens, bool)
                or not isinstance(tokens, int)
                or not 0 <= tokens <= 1_000_000
            ):
                raise ValueError("invalid token usage")
        except (ValueError, KeyError, TypeError, AttributeError):
            raise AiCallError(AiFailureCode.INVALID_OUTPUT) from None
        return AiCompletion(
            provider=self.provider,
            model=self.model,
            output={"vector": [float(value) for value in data[0]["embedding"]]},
            usage=AiTokenUsage(input_tokens=tokens),
            usage_reported=reported,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def close(self) -> None:
        self._client.close()


def create_embedding_client(settings: Settings) -> EmbeddingClient:
    if (
        not settings.ai_enabled
        or not settings.embeddings_enabled
        or settings.embedding_api_key is None
    ):
        raise AiCallError(AiFailureCode.UNAVAILABLE, "embedding is disabled or unconfigured")
    configuration = FrozenEmbeddingConfiguration.from_settings(settings)
    if configuration.currency is None or configuration.input_rate is None:
        raise AiCallError(AiFailureCode.UNAVAILABLE, "embedding price is unknown")
    return EmbeddingClient(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key.get_secret_value(),
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.embedding_timeout_seconds,
        configuration=configuration,
    )
