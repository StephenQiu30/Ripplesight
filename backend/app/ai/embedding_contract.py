"""Independent embedding model, dimensions and input-only price snapshot."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from ai.capability_schemas import AiPriceQuote, FrozenAiModel, digest
from ai.schemas import AiCallError, AiFailureCode
from core.config import Settings


class EmbeddingPricing:
    # Embeddings reserve input cost only; the shared ledger requires a positive output cap.
    output_tokens_limit = 1

    def __init__(self, configuration: FrozenEmbeddingConfiguration):
        self.configuration = configuration

    def quote(self, *, input_tokens_cap: int, output_tokens_cap: int) -> AiPriceQuote:
        if self.configuration.currency is None or self.configuration.input_rate is None:
            raise AiCallError(AiFailureCode.UNAVAILABLE, "embedding price is unknown")
        return AiPriceQuote(
            currency=self.configuration.currency,
            input_tokens_cap=input_tokens_cap,
            output_tokens_cap=1,
            input_rate_micros_per_million=self.configuration.input_rate,
            output_rate_micros_per_million=Decimal(0),
        )


class FrozenEmbeddingConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    endpoint: str
    model: str = Field(min_length=1, max_length=128)
    dimensions: int = Field(ge=0, le=3072)
    currency: Literal["USD", "CNY"] | None
    input_rate: Decimal | None = Field(ge=0)
    configuration_version: Literal[1] = 1

    @classmethod
    def from_settings(cls, settings: Settings) -> FrozenEmbeddingConfiguration:
        return cls(
            endpoint=settings.embedding_base_url.rstrip("/"),
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            currency=settings.embedding_currency,
            input_rate=settings.embedding_input_rate_micros_per_million,
        )

    @property
    def sha256(self) -> str:
        return digest(self.model_dump(mode="json"))

    @property
    def provider(self) -> str:
        host = urlsplit(self.endpoint).hostname
        if host is None or len(host) > 64:
            raise ValueError("embedding provider identity exceeds the ledger")
        return host

    @property
    def model_identity(self) -> FrozenAiModel:
        return FrozenAiModel(
            key="embedding",
            provider=self.provider,
            model=self.model,
            component_key="ai.embeddings",
            vision=False,
            catalog_sha256=self.sha256,
        )

    def scope(self) -> dict[str, str]:
        return {
            "embedding_configuration": self.model_dump_json(),
            "embedding_configuration_hash": self.sha256,
        }
