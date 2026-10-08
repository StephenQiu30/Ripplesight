import httpx
import pytest

from ai.adapters.embeddings import EmbeddingClient, cosine
from ai.schemas import AiCallError


def test_embedding_adapter_posts_real_embeddings_and_validates_index_dimensions_and_usage():
    requests = []

    def controlled(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "controlled",
                "data": [{"index": 0, "embedding": [0.5, 0.5]}],
                "usage": {"prompt_tokens": 12},
            },
        )

    client = EmbeddingClient(
        base_url="https://api.example.com/v1",
        api_key="controlled",
        model="controlled",
        dimensions=2,
        timeout_seconds=5,
        transport=httpx.MockTransport(controlled),
    )
    answer = client.complete(prompt="固定标题\n固定正文", output_schema={})
    assert str(requests[0].url) == "https://api.example.com/v1/embeddings"
    assert answer.output == {"vector": [0.5, 0.5]} and answer.usage.input_tokens == 12
    assert cosine(answer.output["vector"], [1, 1]) == pytest.approx(1)
    client.close()


@pytest.mark.parametrize(
    "data",
    [
        [{"index": 1, "embedding": [1, 0]}],
        [{"index": False, "embedding": [1, 0]}],
        [{"index": 0, "embedding": [1]}],
        [{"index": 0, "embedding": [True, 0]}],
        [{"index": 0, "embedding": ["1", 0]}],
        [{"index": 0, "embedding": [1, 0]}, {"index": 0, "embedding": [0, 1]}],
    ],
)
def test_invalid_embedding_never_returns_a_partial_vector(data):
    client = EmbeddingClient(
        base_url="https://api.example.com/v1",
        api_key="controlled",
        model="controlled",
        dimensions=2,
        timeout_seconds=5,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": data})),
    )
    with pytest.raises(AiCallError, match="invalid_output"):
        client.complete(prompt="fixed", output_schema={})
    client.close()


def test_embedding_configuration_freezes_model_dimensions_and_known_price_without_credentials():
    from decimal import Decimal

    from pydantic import SecretStr

    from ai.adapters.embeddings import FrozenEmbeddingConfiguration, create_embedding_client
    from core.config import Settings

    settings = Settings(
        database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
        ai_enabled=True,
        embeddings_enabled=True,
        embedding_api_key=SecretStr("never-persist"),
        embedding_currency="USD",
        embedding_input_rate_micros_per_million=Decimal("20000"),
    )
    frozen = FrozenEmbeddingConfiguration.from_settings(settings)
    assert "never-persist" not in frozen.model_dump_json()
    client = create_embedding_client(settings)
    assert client.embedding_configuration == frozen
    assert client.pricing_spec.output_tokens_limit == 1
    assert client.pricing_spec.quote(input_tokens_cap=1000, output_tokens_cap=1).cap_micros == 20
    client.close()


def test_embedding_unknown_price_is_closed_before_any_client_is_created():
    from pydantic import SecretStr

    from ai.adapters.embeddings import create_embedding_client
    from core.config import Settings

    with pytest.raises(AiCallError, match="unavailable"):
        create_embedding_client(
            Settings(
                database_url="postgresql+psycopg://test:test@127.0.0.1/hotkey_test",
                ai_enabled=True,
                embeddings_enabled=True,
                embedding_api_key=SecretStr("controlled"),
            )
        )


def test_embedding_missing_usage_does_not_claim_zero_confirmed_cost():
    client = EmbeddingClient(
        base_url="https://api.example.com/v1",
        api_key="controlled",
        model="controlled",
        dimensions=2,
        timeout_seconds=5,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "model": "controlled",
                    "data": [{"index": 0, "embedding": [0.5, 0.5]}],
                },
            )
        ),
    )
    try:
        answer = client.complete(prompt="fixed", output_schema={})
        assert answer.usage_reported is False
    finally:
        client.close()
