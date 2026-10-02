"""AIHOT editorial/selection/writing semantics adapted to strict Python DTOs.

Upstream 035f7b7f6e26cf203562ddd6065ff7adc1bb0c07. Copyright (c) 2026
数字生命卡兹克. MIT license and modification provenance: THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from analysis.editorial_schemas import (
    EditorialCopy,
    EditorialEntityGuardView,
    EditorialMaterial,
    PrefilterLabel,
    SelectionDecision,
)
from analysis.prompts import editorial_prompt_version, render_editorial_prompt

MAX_BODY_CHARS = 60000
THRESHOLDS = {"T1": 60, "T1_5": 65, "T2": 76}
CATEGORIES = {
    "ai-models": ("模型", "新模型、版本、权重、能力与价格的发布和评测"),
    "ai-products": ("产品", "AI产品、功能、应用、工具、API与平台的发布更新"),
    "industry": ("行业", "经营、融资并购、人事、合作、诉讼、政策、市场与基础设施"),
    "paper": ("论文", "研究论文、技术报告、基准与数据集"),
    "tip": ("教程", "教程、实践经验、使用技巧、提示词与工具用法、技术讲解"),
    "opinion": ("观点", "人物观点、评论、分析、访谈、现象与趋势讨论"),
}
CATEGORY_TAGS = (
    "产品更新",
    "模型发布",
    "论文/研究",
    "开源/仓库",
    "教程/实践",
    "现象/趋势",
    "大佬观点",
    "评测/基准",
    "安全/对齐",
    "行业动态",
    "政策/监管",
    "非AI/通用工具",
    "其他",
)
TOPIC_TAGS = (
    "Agent",
    "编码",
    "推理",
    "多模态",
    "语音",
    "视频",
    "图像生成",
    "RAG",
    "端侧",
    "数据/训练",
    "搜索",
    "部署/工程",
    "开源生态",
    "具身智能",
    "MCP/工具调用",
)
ENTITY_TAGS = (
    "OpenAI",
    "Anthropic",
    "DeepSeek",
    "DeepMind",
    "Google",
    "Meta",
    "Microsoft",
    "xAI",
    "Hugging Face",
    "GitHub",
    "arXiv",
)
ENTITIES: dict[str, tuple[str, str | None, tuple[str, ...]]] = {
    "openai": ("OpenAI", "OpenAI", ("OpenAI", "ChatGPT", "Sora", "Codex", "GPT")),
    "anthropic": ("Anthropic", "Anthropic", ("Anthropic", "Claude")),
    "google": ("Google", "Google", ("Google", "DeepMind", "Gemini", "谷歌")),
    "deepseek": ("DeepSeek", "DeepSeek", ("DeepSeek", "深度求索")),
    "qwen": ("千问 Qwen", None, ("Qwen", "通义", "阿里")),
    "kimi": ("Kimi / 月之暗面", None, ("Kimi", "月之暗面", "Moonshot")),
    "minimax": ("MiniMax", None, ("MiniMax", "海螺")),
    "zhipu": ("智谱 GLM", None, ("智谱", "GLM", "Z.ai")),
    "xai": ("xAI", "xAI", ("xAI", "Grok")),
    "meta": ("Meta", "Meta", ("Meta", "Llama")),
    "microsoft": ("Microsoft", "Microsoft", ("Microsoft", "微软", "Copilot")),
    "nvidia": ("NVIDIA", None, ("NVIDIA", "英伟达")),
    "hugging-face": ("Hugging Face", "Hugging Face", ("Hugging Face",)),
    "cursor": ("Cursor", None, ("Cursor", "Anysphere")),
    "openrouter": ("OpenRouter", None, ("OpenRouter",)),
}
_IDENTITY_PATTERNS = {
    "openai": r"openai|chatgpt|\bgpt-?[o\d]|\bsora\b|\bcodex\b",
    "anthropic": (
        r"anthropic|\bclaude\b|\b(?:opus|sonnet|haiku)\s*\d+(?:[.\-]\d+)*\b"
        r"|\bfable\s*\d+(?:[.\-]\d+)*\b|\bmythos\b"
    ),
    "google": r"google|deepmind|\bgemini\b|notebooklm|\bveo\s?\d|\balphafold\b|\bamie\b",
    "deepseek": r"deepseek|深度求索",
    "xai": r"\bxai\b|\bgrok\b",
    "meta": r"\bmeta\s?ai\b|\bllama\b",
    "microsoft": r"microsoft|copilot|微软",
    "nvidia": r"nvidia|英伟达|\bnemotron\b|\bnemo\b|\bblackwell\b|\brubin(?:\s+ultra)?\b|\bcuda\b",
    "qwen": r"\bqwen|通义|千问",
    "hugging-face": r"hugging\s?face",
    "cursor": r"\bCursor\b",
    "kimi": r"\bkimi\b|月之暗面|\bmoonshot\s?ai\b",
    "openrouter": r"openrouter",
    "minimax": r"minimax",
    "zhipu": r"智谱|\bglm-?[4-9]",
    "hunyuan": r"混元|hunyuan",
    "doubao": r"豆包|doubao|字节跳动|bytedance",
    "mistral": r"mistral",
    "perplexity": r"\bPerplexity\b",
    "runway": r"\brunway\b",
    "suno": r"\bsuno\b",
    "midjourney": r"midjourney",
    "stability-ai": r"stability\s?ai",
    "elevenlabs": r"eleven\s?labs",
    "vllm": r"\bvllm\b",
    "ollama": r"\bollama\b",
    "windsurf": r"windsurf",
    "devin": r"\bdevin\b",
    "manus": r"\bmanus\b",
    "apple": r"\bapple\s?(intelligence|silicon|ai)\b|苹果(智能|\s?AI)",
    "amazon": r"amazon|\baws\b|亚马逊",
    "baidu": r"百度|baidu|文心|\bernie\s?bot\b",
}
PUBLISHER_DOMAINS = {
    "openai": ("openai.com",),
    "anthropic": ("anthropic.com", "claude.com"),
    "google": ("deepmind.google", "ai.google", "blog.google"),
    "deepseek": ("deepseek.com",),
    "xai": ("x.ai",),
    "meta": ("ai.meta.com",),
    "microsoft": ("microsoft.com",),
    "nvidia": ("nvidia.com",),
    "qwen": ("qwen.ai",),
    "cursor": ("cursor.com",),
    "openrouter": ("openrouter.ai",),
}
CATEGORY_BY_ITEM_TYPE = {
    "model_release": "模型发布",
    "product_launch": "产品更新",
    "tool_or_prompt": "教程/实践",
    "research_paper": "论文/研究",
    "industry_event": "行业动态",
    "opinion_analysis": "大佬观点",
    "tutorial_explainer": "教程/实践",
}
TAG_SYNONYMS = {
    "教程/玩法": "教程/实践",
    "技巧/最佳实践": "教程/实践",
    "合作/生态": "行业动态",
    "融资/收购": "行业动态",
    "公司动态": "行业动态",
    "合作": "行业动态",
    "生态": "行业动态",
    "融资": "行业动态",
    "收购": "行业动态",
    "投资": "行业动态",
    "并购": "行业动态",
    "政策": "政策/监管",
    "监管": "政策/监管",
    "法规": "政策/监管",
    "安全": "安全/对齐",
    "对齐": "安全/对齐",
    "论文": "论文/研究",
    "研究": "论文/研究",
    "paper": "论文/研究",
    "papers": "论文/研究",
    "open-source": "开源/仓库",
    "开源": "开源/仓库",
    "仓库": "开源/仓库",
    "repo": "开源/仓库",
    "教程": "教程/实践",
    "玩法": "教程/实践",
    "指南": "教程/实践",
    "技巧": "教程/实践",
    "最佳实践": "教程/实践",
    "实践": "教程/实践",
    "产品": "产品更新",
    "更新": "产品更新",
    "发布": "模型发布",
    "模型": "模型发布",
    "趋势": "现象/趋势",
    "现象": "现象/趋势",
    "观点": "大佬观点",
    "视频生成": "视频",
    "非ai": "非AI/通用工具",
    "non-ai": "非AI/通用工具",
    "通用工具": "非AI/通用工具",
    "工程工具": "非AI/通用工具",
    "安全扫描": "非AI/通用工具",
    "devops": "非AI/通用工具",
    "行业": "行业动态",
    "动态": "行业动态",
}


def normalize_tags(tags: list[str], fallback: str = "其他") -> list[str]:
    known = {*CATEGORY_TAGS, *TOPIC_TAGS, *ENTITY_TAGS}
    normalized = [
        TAG_SYNONYMS.get(tag.strip().lower(), TAG_SYNONYMS.get(tag.strip(), tag.strip()))
        for tag in tags
    ]
    categories = [tag for tag in normalized if tag in CATEGORY_TAGS]
    category = categories[0] if categories else fallback
    return [
        category,
        *list(
            dict.fromkeys(tag for tag in normalized if tag in known and tag not in CATEGORY_TAGS)
        )[:5],
    ]


def decide_selection(tier: str, scores: tuple[int, ...]) -> SelectionDecision:
    threshold = THRESHOLDS.get(tier)
    if any(type(score) is not int or not 0 <= score <= 100 for score in scores) or len(scores) > 2:
        raise ValueError("invalid independent scores")
    complete = len(scores) == 2 if threshold is not None else not scores
    total = sum(scores) if complete and threshold is not None else None
    return SelectionDecision(
        complete=complete,
        threshold=threshold,
        score=None if total is None else total // 2,
        selected=total is not None and threshold is not None and total >= threshold * 2,
        understand=total is not None
        and (total > 100 or (threshold is not None and total >= threshold * 2)),
    )


def normalize_prefilter(label: PrefilterLabel, material: EditorialMaterial) -> PrefilterLabel:
    evidence = material.body.strip() or material.excerpt.strip() or material.quoted_text.strip()
    return "UNKNOWN" if label == "BLOCK" and not evidence else label


def looks_zh(text: str) -> bool:
    return bool(re.search(r"[一-鿿]", text)) and not re.search(r"[぀-ヿ가-힯]", text)


def is_short_post(material: EditorialMaterial) -> bool:
    text = material.body or material.title
    cjk = len(re.findall(r"[一-鿿]", text))
    return (
        material.source_kind == "x_search"
        and bool(text)
        and len(text) < (100 if cjk > len(text) * 0.3 else 500)
    )


def needs_short_post_translation(text: str) -> bool:
    clean = re.sub(r"https?://\S+|@[A-Za-z0-9_]+|#[A-Za-z0-9_]+", " ", text)
    count = len(re.sub(r"\s", "", clean))
    if not looks_zh(clean) or not count or len(re.findall(r"[一-鿿]", clean)) / count < 0.65:
        return True
    return any(
        len(re.sub(r"\s", "", run)) >= 10
        for run in re.findall(r"[A-Za-z][A-Za-z0-9+.#/-]*(?:\s+[A-Za-z][A-Za-z0-9+.#/-]*)+", clean)
    )


def clean_article_text(text: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>|https?://\S+", " ", text, flags=re.I)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def score_input(material: EditorialMaterial) -> str:
    body = (material.body or material.excerpt or material.title).strip()
    if material.source_kind == "x_search" and material.quoted_text:
        body += f"\n\n[引用 @{material.quoted_author or '原推文'}]\uff1a{material.quoted_text}"
    instant = material.published_at or material.discovered_at
    at = instant.astimezone(ZoneInfo("Asia/Shanghai"))
    precision = "milliseconds" if at.microsecond else "seconds"
    return "\n\n".join(
        (
            "请按系统规则评估以下单篇材料所代表的事件。只输出 attentionScore。",
            f"【发布时间\uff08北京时间\uff09】\n{at.isoformat(timespec=precision)}",
            f"【标题】\n{material.title.strip()}",
            f"【完整正文】\n{body[:MAX_BODY_CHARS]}",
        )
    )


def render_material(material: EditorialMaterial) -> str:
    quality = (
        "完整正文"
        if material.body_complete
        else "部分正文"
        if material.body
        else "仅摘要"
        if material.excerpt
        else "无有效正文"
    )
    lines = [
        f"【来源】{material.source_name}\uff08{material.source_kind}\uff0ctier={material.tier}\uff09"
    ]
    if material.source_tags:
        lines.append(f"【来源标签】{', '.join(material.source_tags)}")
    if material.author:
        lines.append(f"【作者】{material.author}")
    if material.published_at:
        lines.append(f"【发布时间】{material.published_at.isoformat()}")
    if material.image_count or material.video_count:
        lines.append(
            f"【媒体】{material.image_count}张图 · {material.video_count}个视频"
            "\uff08未读取媒体内容\uff09"
        )
    lines.extend(
        (f"【原文链接】{material.url}", f"【标题】{material.title}", f"【材料质量】{quality}")
    )
    if material.quoted_text:
        lines.append(
            f"【引用\uff08独立来源\uff0c勿当主帖逐句展开\uff09】@{material.quoted_author}\n{material.quoted_text[:2000]}"
        )
    lines.append(f"【正文】\n{(material.body or material.excerpt)[:MAX_BODY_CHARS]}")
    return "\n".join(lines)


def match_entity_ids(text: str) -> list[str]:
    variants = re.sub(r"\b(gpt|glm)\s+(?=[o\d])", r"\1-", text, flags=re.I)
    matched = [
        key
        for key, pattern in _IDENTITY_PATTERNS.items()
        if re.search(pattern, variants, flags=0 if key in {"cursor", "perplexity"} else re.I)
    ]
    if re.search(r"\bMeta\b|@AIatMeta\b", text) and "meta" not in matched:
        matched.append("meta")
    if re.search(r"\bZhipu(?:\s+AI\b|['\u2019]s\b)", text, re.I) and "zhipu" not in matched:
        matched.append("zhipu")
    return matched


def identity_context(material: EditorialMaterial) -> tuple[set[str], str]:
    texts = (
        material.title,
        material.body,
        material.excerpt,
        material.quoted_text,
        material.source_name,
    )
    allowed = set(match_entity_ids("\n".join(texts)))
    host = urlsplit(material.url).hostname or ""
    publisher = next(
        (
            key
            for key, domains in PUBLISHER_DOMAINS.items()
            if any(
                host.lower() == domain or host.lower().endswith("." + domain) for domain in domains
            )
        ),
        None,
    )
    facts: list[str] = []
    if publisher:
        allowed.add(publisher)
        facts.append(f"文档发布域主体={ENTITIES[publisher][0]}")
    if material.owner_entity_id in ENTITIES:
        assert material.owner_entity_id is not None
        allowed.add(material.owner_entity_id)
        facts.append(f"来源账号主体={ENTITIES[material.owner_entity_id][0]}")
    return allowed, render_editorial_prompt(
        "identity-context", {"facts": "\uff1b".join(facts) or "未识别到明确发布主体"}
    )


def compact_summary(summary: str, maximum: int = 190) -> str:
    text = re.sub(r"\s*\n+\s*", " ", summary.strip())
    if len(text) <= maximum:
        return text
    for pattern in (
        r"[^。\uff01\uff1f!?]+[。\uff01\uff1f!?]?",
        r"[^\uff0c\uff1b\uff1a、,;:]+[\uff0c\uff1b\uff1a、,;:]?",
    ):
        result = ""
        for part in re.findall(pattern, text):
            if len(result + part) + (1 if pattern.startswith(r"[^\uff0c") else 0) > maximum:
                break
            result += part
            if len(result) >= 80:
                break
        if len(result) >= 50:
            return (
                result.strip()
                if pattern.startswith(r"[^。")
                else re.sub(r"[\uff0c\uff1b\uff1a、,;:]$", "", result) + "。"
            )
    return text


def finalize_copy(material: EditorialMaterial, title: str, summary: str) -> EditorialCopy:
    title = re.sub(r"\s+", " ", title).strip()
    summary = summary.strip() if is_short_post(material) else compact_summary(summary)
    allowed, _ = identity_context(material)
    unsupported_title = [key for key in match_entity_ids(title) if key not in allowed]
    unsupported_summary = [key for key in match_entity_ids(summary) if key not in allowed]
    return EditorialCopy(
        title_zh=material.title
        if unsupported_title and looks_zh(material.title)
        else ""
        if unsupported_title
        else title,
        summary_zh="" if unsupported_summary else summary,
        identity_guard=EditorialEntityGuardView(
            outcome="fallback" if unsupported_title or unsupported_summary else "pass",
            unsupported_title_entity_ids=unsupported_title,
            unsupported_summary_entity_ids=unsupported_summary,
        ),
    )


def structure_instructions() -> str:
    return render_editorial_prompt(
        "structure",
        {
            "categoryCount": "六",
            "categoryGuide": "\n".join(
                f"{key}\uff08{name}\uff09\uff1a{guide}" for key, (name, guide) in CATEGORIES.items()
            ),
            "categoryTags": "、".join(CATEGORY_TAGS),
            "topicTags": "、".join(TOPIC_TAGS),
            "entityTags": "、".join(ENTITY_TAGS),
            "entities": "\uff0c".join(
                f"{key}\uff08{'/'.join(aliases[:3])}\uff09"
                for key, (_, _, aliases) in ENTITIES.items()
            ),
        },
    )


def summarize_prompt(material: EditorialMaterial, now: datetime) -> str:
    _, identity = identity_context(material)
    values = {"sourceName": material.source_name, "identity": identity}
    if material.source_kind == "x_search":
        name = "summarize-short-post" if is_short_post(material) else "summarize-long-post"
        text = render_editorial_prompt(
            name, {**values, "post": (material.body or material.title)[:4000]}
        )
        if material.quoted_text:
            text += "\n\n" + render_editorial_prompt(
                f"{name}-quoted",
                {
                    "quotedLabel": "@" + material.quoted_author
                    if material.quoted_author
                    else "引用推文",
                    "quotedText": material.quoted_text[:1500],
                },
            )
        return text
    date = (
        material.published_at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
        if material.published_at
        else "未注明"
    )
    body = clean_article_text(material.body or material.excerpt)
    return render_editorial_prompt(
        "summarize-article",
        {
            **values,
            "publishedDate": date,
            "today": now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            "title": material.title,
            "body": body[:6000] if body else render_editorial_prompt("summarize-article-empty"),
        },
    )


def pipeline_version() -> str:
    import hashlib

    versions = [
        editorial_prompt_version(name)
        for name in (
            "prefilter",
            "selection-score",
            "structure",
            "understand",
            "summarize-article",
            "summarize-article-empty",
            "summarize-short-post",
            "summarize-short-post-quoted",
            "summarize-long-post",
            "summarize-long-post-quoted",
            "identity-context",
        )
    ]
    rules = json.dumps(
        {
            "thresholds": THRESHOLDS,
            "understand_floor": 50,
            "categories": CATEGORIES,
            "entities": ENTITIES,
            "tags": [CATEGORY_TAGS, TOPIC_TAGS, ENTITY_TAGS],
            "synonyms": TAG_SYNONYMS,
            "identity": _IDENTITY_PATTERNS,
            "publishers": PUBLISHER_DOMAINS,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "editorial.v1@" + hashlib.sha256(("+".join(versions) + rules).encode()).hexdigest()[:20]
