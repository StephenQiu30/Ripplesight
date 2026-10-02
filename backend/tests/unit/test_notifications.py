from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from core.config import Settings
from notifications.feishu import (
    FeishuDeliveryError,
    FeishuWebhook,
    report_card,
    sign,
    validate_webhook_url,
)
from reports.schemas import (
    DailyReportData,
    ReportComparison,
    ReportContentItem,
    ReportCoverage,
    ReportOverview,
    ReportSentiment,
)

NOW = datetime(2026, 9, 26, 1, tzinfo=UTC)
OWNER = uuid4()
TOPIC = uuid4()
REPORT = uuid4()
TARGET = uuid4()
DELIVERY = uuid4()
WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/test-token"


def _data() -> DailyReportData:
    return DailyReportData(
        topic_id=TOPIC,
        topic_name="测试主题",
        window_start=NOW - timedelta(days=1),
        window_end=NOW,
        cutoff_at=NOW,
        overview=ReportOverview(
            posts=ReportComparison(current=4, previous=2, delta=2),
            comments=ReportComparison(current=8, previous=3, delta=5),
            platform_distribution={"hackernews": 4},
            sentiment_distribution={
                ReportSentiment.POSITIVE: 3,
                ReportSentiment.NEUTRAL: 1,
                ReportSentiment.NEGATIVE: 0,
            },
        ),
        top_contents=tuple(
            ReportContentItem(
                citation=f"c{index}",
                content_id=uuid4(),
                content_version_id=uuid4(),
                title=f"标题 {index}",
                summary="摘要",
                sentiment=ReportSentiment.POSITIVE,
                source_key="hackernews",
                url=f"https://example.com/posts/{index}",
                interaction_count=10,
                representative_comments=(),
            )
            for index in range(1, 5)
        ),
        risks=(),
        voices=(),
        coverage=ReportCoverage(sources=(), discovered_at_count=4, unanalyzed_count=0),
    )


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql+psycopg://test:test@127.0.0.1:5432/test",
        "notifications_enabled": True,
        "feishu_webhook_url": SecretStr(WEBHOOK),
        "feishu_secret": SecretStr("private-signing-secret"),
    }
    values.update(overrides)
    return Settings(**values)


def test_feishu_card_and_signature_with_fake_transport(caplog: pytest.LogCaptureFixture) -> None:
    card = report_card(
        _data(),
        report_id=REPORT,
        generator="model",
        web_base_url="https://hotkey.example",
        vault_name="My Vault",
        export_relative_path="HotKey/日报/测试.md",
    )
    elements = card["card"]["elements"]
    assert card["msg_type"] == "interactive"
    assert "测试主题" in card["card"]["header"]["title"]["content"]
    assert "2026-09-26" in elements[0]["text"]["content"]
    assert "模型版" in elements[0]["text"]["content"]
    assert "相关帖子 4" in elements[1]["text"]["content"]
    assert len([item for item in elements if item["tag"] == "div"]) == 5
    assert "https://example.com/posts/3" in elements[4]["text"]["content"]
    buttons = elements[-1]["actions"]
    assert buttons[0]["url"] == f"https://hotkey.example/reports/{REPORT}"
    assert buttons[1]["url"] == (
        "obsidian://open?vault=My%20Vault&file=HotKey%2F%E6%97%A5%E6%8A%A5%2F%E6%B5%8B%E8%AF%95"
    )
    without_export = report_card(
        _data(),
        report_id=REPORT,
        generator="template",
        web_base_url="http://127.0.0.1:8666",
        vault_name="Vault",
        export_relative_path=None,
    )
    assert len(without_export["card"]["elements"][-1]["actions"]) == 1

    requests: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(__import__("json").loads(request.content))
        return httpx.Response(200, json={"code": 0})

    caplog.set_level(logging.INFO)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        FeishuWebhook(
            url=SecretStr(WEBHOOK), secret=SecretStr("private-signing-secret"), client=client
        ).send(card, now=NOW)
    assert len(requests) == 1
    assert requests[0]["timestamp"] == str(int(NOW.timestamp()))
    assert requests[0]["sign"] == sign(int(NOW.timestamp()), SecretStr("private-signing-secret"))
    assert requests[0]["sign"] == "lpaI/B0j7BTUTMosIKG+SYJs7MNL+1jvWBY2J91cXEk="
    assert "private-signing-secret" not in caplog.text
    assert "test-token" not in caplog.text


def test_webhook_url_rejects_lookalike_hosts_and_insecure_urls() -> None:
    for url in (
        "http://open.feishu.cn/open-apis/bot/v2/hook/secret",
        "https://open.feishu.cn.evil.example/open-apis/bot/v2/hook/secret",
        "https://open.feishu.cn@evil.example/open-apis/bot/v2/hook/secret",
    ):
        with pytest.raises(ValueError, match="invalid Feishu webhook URL"):
            validate_webhook_url(url)


@pytest.mark.parametrize(
    ("response", "error_code", "uncertain"),
    [
        (httpx.Response(400), "feishu_client_error", False),
        (httpx.Response(200, json={"code": 19021}), "feishu_api_error", False),
        (httpx.Response(500), "feishu_response_uncertain", True),
    ],
)
def test_feishu_rejects_non_success(
    response: httpx.Response, error_code: str, uncertain: bool
) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: response)) as client,
        pytest.raises(FeishuDeliveryError) as caught,
    ):
        FeishuWebhook(url=SecretStr(WEBHOOK), secret=None, client=client).send(
            {"msg_type": "interactive", "card": {}}, now=NOW
        )
    assert caught.value.code == error_code
    assert caught.value.uncertain is uncertain
    assert "test-token" not in repr(caught.value)
