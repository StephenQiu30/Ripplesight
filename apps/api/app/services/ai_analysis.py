from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.api.app.core.settings import settings
from apps.api.app.models.hotspot import Hotspot
from apps.api.app.models.keyword import Keyword
from apps.api.app.services.ai.providers import BaseLLMProvider, LLMResult, build_provider


@dataclass(slots=True)
class AnalysisResult:
    is_real: bool | None
    relevance_score: float
    relevance_reason: str
    keyword_mentioned: bool
    importance: str
    summary: str
    model_name: str
    raw_response: dict[str, Any]
    quick_understanding: list[str] = field(default_factory=list)
    topic_ideas: list[dict[str, str]] = field(default_factory=list)
    used_fallback: bool = False
    prompt_name: str | None = None
    token_usage: dict[str, int] | None = None
    provider: str = ""


def _select_provider() -> BaseLLMProvider:
    configured = settings.ai_provider.strip().lower() if settings.ai_provider else "fallback"
    try:
        return build_provider(configured)
    except Exception:
        return build_provider("fallback")


def analyze_hotspot(hotspot: Hotspot, keyword: Keyword | None) -> AnalysisResult:
    provider = _select_provider()
    try:
        return _to_analysis_result(provider.analyze(hotspot, keyword))
    except Exception as exc:  # noqa: BLE001
        if provider.__class__.__name__ == "FallbackLLMProvider":
            raise
        fallback = _fallback_analysis(hotspot, keyword)
        fallback.raw_response = {"provider": "fallback", "reason": str(exc)}
        fallback.used_fallback = True
        return fallback


def expand_keyword_queries(keyword: Keyword) -> list[str]:
    provider = _select_provider()
    base_query = keyword.query_template or keyword.keyword
    try:
        return _dedupe_queries(provider.expand_queries(keyword, base_query))[:5]
    except Exception:  # noqa: BLE001
        fallback = _fallback_queries(keyword, base_query)
        return fallback


def is_analysis_active(result: AnalysisResult) -> bool:
    return result.relevance_score >= settings.relevance_threshold and result.is_real is not False


def _to_analysis_result(llm_result: LLMResult) -> AnalysisResult:
    usage = llm_result.token_usage
    return AnalysisResult(
        is_real=llm_result.is_real,
        relevance_score=llm_result.relevance_score,
        relevance_reason=llm_result.relevance_reason,
        keyword_mentioned=llm_result.keyword_mentioned,
        importance=llm_result.importance,
        summary=llm_result.summary,
        model_name=llm_result.model_name,
        raw_response=llm_result.raw_response,
        quick_understanding=llm_result.quick_understanding,
        topic_ideas=llm_result.topic_ideas,
        used_fallback=llm_result.used_fallback,
        prompt_name=llm_result.prompt_name,
        token_usage=usage,
        provider=llm_result.provider,
    )


def _fallback_analysis(hotspot: Hotspot, keyword: Keyword | None) -> AnalysisResult:
    text = f"{hotspot.title} {hotspot.snippet or ''}".lower()
    keyword_text = (keyword.keyword if keyword else "").lower()
    mentioned = bool(keyword_text and keyword_text in text)
    score = 80.0 if mentioned else 45.0
    importance = "high" if score >= 80 else "medium" if score >= 50 else "low"
    summary = hotspot.snippet or hotspot.title
    quick_understanding = _build_quick_understanding(hotspot, keyword, score, summary)
    topic_ideas = _build_topic_ideas(hotspot, keyword)
    return AnalysisResult(
        is_real=True,
        relevance_score=score,
        relevance_reason="本地降级分析：根据标题和摘要中是否包含关键词判断相关性。",
        keyword_mentioned=mentioned,
        importance=importance,
        summary=summary,
        model_name=settings.openai_model or "local-fallback",
        raw_response={
            "provider": "fallback",
            "quick_understanding": quick_understanding,
            "topic_ideas": topic_ideas,
        },
        quick_understanding=quick_understanding,
        topic_ideas=topic_ideas,
        used_fallback=not (settings.openai_api_key and settings.openai_model),
        prompt_name="fallback",
        token_usage=None,
        provider="fallback",
    )


def _build_quick_understanding(hotspot: Hotspot, keyword: Keyword | None, score: float, summary: str) -> list[str]:
    keyword_text = keyword.keyword if keyword else "当前热点"
    return [
        f"{keyword_text}相关热点：{hotspot.title}",
        f"相关性评分 {score:.0f}/100，可优先用于快速理解与选题判断。",
        f"核心信息：{summary}",
    ]


def _build_topic_ideas(hotspot: Hotspot, keyword: Keyword | None) -> list[dict[str, str]]:
    keyword_text = keyword.keyword if keyword else "热点"
    title = hotspot.title.strip()
    return [
        {
            "title": f"3分钟看懂：{title}",
            "angle": "快速解释热点背景、变化和受众影响。",
            "format": "短视频/图文",
            "rationale": "适合内容创作者把热点转成快速理解型内容。",
        },
        {
            "title": f"{keyword_text}为什么值得关注",
            "angle": "拆解趋势信号、受益人群和后续观察点。",
            "format": "长图文/直播提纲",
            "rationale": "适合做观点型或深度解读型选题。",
        },
    ]


def _fallback_queries(keyword: Keyword, base_query: str) -> list[str]:
    return _dedupe_queries(
        [
            base_query,
            f"{keyword.keyword} AI",
            f"{keyword.keyword} news",
            f"{keyword.keyword} launch",
            f"{keyword.keyword} update",
        ]
    )


def _dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for query in queries:
        normalized = query.strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result
