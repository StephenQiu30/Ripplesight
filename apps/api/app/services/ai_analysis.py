from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from apps.api.app.core.settings import settings
from apps.api.app.models.hotspot import Hotspot
from apps.api.app.models.keyword import Keyword


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
    used_fallback: bool = False


def analyze_hotspot(hotspot: Hotspot, keyword: Keyword | None) -> AnalysisResult:
    if settings.openai_api_key and settings.openai_model:
        try:
            return _analyze_with_model(hotspot, keyword)
        except Exception as exc:  # noqa: BLE001
            fallback = _fallback_analysis(hotspot, keyword)
            fallback.raw_response = {"provider": "fallback", "reason": str(exc)}
            fallback.used_fallback = True
            return fallback
    return _fallback_analysis(hotspot, keyword)


def expand_keyword_queries(keyword: Keyword) -> list[str]:
    base_query = keyword.query_template or keyword.keyword
    if settings.openai_api_key and settings.openai_model:
        try:
            return _expand_with_model(keyword, base_query)
        except Exception:  # noqa: BLE001
            return _fallback_queries(keyword, base_query)
    return _fallback_queries(keyword, base_query)


def is_analysis_active(result: AnalysisResult) -> bool:
    return result.relevance_score >= settings.relevance_threshold and result.is_real is not False


def _expand_with_model(keyword: Keyword, base_query: str) -> list[str]:
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": "You expand hotspot monitoring keywords into concise search queries."},
            {
                "role": "user",
                "content": (
                    "Return strict JSON with key queries as an array of 2 to 5 short search queries. "
                    f"Keyword: {keyword.keyword}\nTemplate: {base_query}"
                ),
            },
        ],
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
    base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    response = httpx.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=20)
    response.raise_for_status()
    raw = response.json()
    content = raw["choices"][0]["message"]["content"]
    parsed = _parse_model_json(content)
    queries = [str(item).strip() for item in parsed.get("queries", []) if str(item).strip()]
    return _dedupe_queries([base_query, *queries])[:5]


def _fallback_queries(keyword: Keyword, base_query: str) -> list[str]:
    return _dedupe_queries(
        [
            base_query,
            f"{keyword.keyword} AI",
            f"{keyword.keyword} news",
            f"{keyword.keyword} launch",
            f"{keyword.keyword} update",
        ]
    )[:5]


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


def _analyze_with_model(hotspot: Hotspot, keyword: Keyword | None) -> AnalysisResult:
    prompt = (
        "Analyze this hotspot candidate. Return strict JSON with keys: "
        "is_real, relevance_score, relevance_reason, keyword_mentioned, importance, summary. "
        "importance must be low, medium, or high. relevance_score is 0-100. "
        "summary and relevance_reason must be written in Chinese.\n\n"
        f"Keyword: {keyword.keyword if keyword else ''}\n"
        f"Title: {hotspot.title}\n"
        f"Snippet: {hotspot.snippet or ''}\n"
        f"URL: {hotspot.url}"
    )
    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": "You are a precise news relevance analyst."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
    base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    response = httpx.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    raw = response.json()
    content = raw["choices"][0]["message"]["content"]
    parsed = _parse_model_json(content)
    return AnalysisResult(
        is_real=parsed.get("is_real"),
        relevance_score=float(parsed.get("relevance_score", 0)),
        relevance_reason=str(parsed.get("relevance_reason") or ""),
        keyword_mentioned=bool(parsed.get("keyword_mentioned")),
        importance=str(parsed.get("importance") or "medium"),
        summary=str(parsed.get("summary") or hotspot.snippet or hotspot.title),
        model_name=settings.openai_model or "unknown",
        raw_response=raw,
    )


def _fallback_analysis(hotspot: Hotspot, keyword: Keyword | None) -> AnalysisResult:
    text = f"{hotspot.title} {hotspot.snippet or ''}".lower()
    keyword_text = (keyword.keyword if keyword else "").lower()
    mentioned = bool(keyword_text and keyword_text in text)
    score = 80.0 if mentioned else 45.0
    importance = "high" if score >= 80 else "medium" if score >= 50 else "low"
    return AnalysisResult(
        is_real=True,
        relevance_score=score,
        relevance_reason="本地降级分析：根据标题和摘要中是否包含关键词判断相关性。",
        keyword_mentioned=mentioned,
        importance=importance,
        summary=hotspot.snippet or hotspot.title,
        model_name=settings.openai_model or "local-fallback",
        raw_response={"provider": "fallback"},
        used_fallback=not (settings.openai_api_key and settings.openai_model),
    )


def _parse_model_json(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise
