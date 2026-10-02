from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai.capability_schemas import AI_CAPABILITIES, AiModelServerSpec, capability_for_purpose


def test_all_eleven_capabilities_map_real_purposes_and_legacy_stage_names():
    assert len(AI_CAPABILITIES) == 11
    assert capability_for_purpose("editorial.score_1") == "score"
    assert capability_for_purpose("editorial.score_2") == "score"
    assert capability_for_purpose("editorial.structure") == "structure"
    assert capability_for_purpose("editorial.understand") == "understand"
    assert capability_for_purpose("editorial.summarize") == "summarize"
    assert capability_for_purpose("story.group_review") == "groupReview"
    assert capability_for_purpose("story.digest") == "digest"
    assert capability_for_purpose("report.edition.monthly") == "report"
    assert capability_for_purpose("publication.translate") == "translate"
    assert capability_for_purpose("monitor.recognize") == "monitor"


def test_model_server_credentials_never_serialize_and_price_has_independent_currency():
    model = AiModelServerSpec(
        transport="openai_compatible",
        provider_key="controlled",
        model="controlled-v1",
        base_url="https://models.example/v1",
        api_key="controlled-secret",
        currency="CNY",
        input_rate_micros_per_million=Decimal("1000000"),
        output_rate_micros_per_million=Decimal("2000000"),
    )
    assert "controlled-secret" not in model.model_dump_json()
    assert "controlled-secret" not in repr(model)
    assert model.component_key == "ai.llm.controlled"
    assert model.quote(input_tokens_cap=10, output_tokens_cap=20).cap_micros == 50
    assert model.quote(input_tokens_cap=10, output_tokens_cap=20).currency == "CNY"
    with pytest.raises(ValidationError):
        AiModelServerSpec(
            transport="openai_compatible", provider_key="controlled", model="x", timeout_seconds=601
        )
