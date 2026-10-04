# ruff: noqa: RUF001
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from reports.schemas import (
    DailyReportData,
    ReportKind,
    ReportSection,
    ReportSentiment,
    SourceCoverageStatus,
)

_REPORT_TIMEZONE = ZoneInfo("Asia/Shanghai")
_SENTIMENT_LABELS = {
    ReportSentiment.POSITIVE: "正面",
    ReportSentiment.NEUTRAL: "中性",
    ReportSentiment.NEGATIVE: "负面",
}
_COVERAGE_LABELS = {
    SourceCoverageStatus.SUCCEEDED: "成功",
    SourceCoverageStatus.PARTIAL: "部分成功",
    SourceCoverageStatus.FAILED: "失败",
    SourceCoverageStatus.INCOMPLETE: "进行中",
    SourceCoverageStatus.MISSING: "无采集记录",
}


def _local_minute(value: datetime) -> str:
    return value.astimezone(_REPORT_TIMEZONE).strftime("%Y-%m-%d %H:%M")


def _inline(value: str) -> str:
    normalized = " ".join(value.split())
    for character in ("\\", "`", "*", "_", "[", "]", "<", ">"):
        normalized = normalized.replace(character, f"\\{character}")
    return normalized


def _link(label: str, url: str | None) -> str:
    safe_label = _inline(label)
    return f"[{safe_label}](<{url}>)" if url is not None else safe_label


def _comparison(delta: int) -> str:
    if delta > 0:
        return f"+{delta}"
    if delta < 0:
        return str(delta)
    return "持平"


def _distribution(values: dict[str, int]) -> str:
    if not values:
        return "无"
    return "、".join(f"{key} {values[key]}" for key in sorted(values))


def _narrative(data: DailyReportData, section: ReportSection) -> list[str]:
    urls = {item.citation: item.url for item in data.top_contents}
    lines: list[str] = []
    for sentence in data.narratives.get(section, ()):
        references = " ".join(
            _link(f"[{citation}]", urls[citation]) for citation in sentence.citations
        )
        lines.append(f"{_inline(sentence.text)} {references}")
    if lines:
        lines.append("")
    return lines


def render_daily_report(data: DailyReportData) -> str:
    """Render the frozen structured report without consulting mutable state."""
    weekly = data.kind is ReportKind.WEEKLY
    label, previous_label = ("周报", "前一周") if weekly else ("日报", "前一日")
    window_label = (
        f"> 数据窗口：{_local_minute(data.window_start)}—"
        f"{_local_minute(data.window_end)}（Asia/Shanghai）"
    )
    posts_comparison = _comparison(data.overview.posts.delta)
    comments_comparison = _comparison(data.overview.comments.delta)
    pending_without_analysis = bool(data.pending_contents) and data.overview.posts.current == 0
    overview_lines = (
        [
            f"- 待分析材料：{len(data.pending_contents)} 条",
            "- 相关性与情感尚待分析，暂不作趋势比较。",
            "- 评论摘录与采样范围见下方材料和覆盖说明。",
        ]
        if pending_without_analysis
        else [
            f"- 相关帖子：{data.overview.posts.current}"
            + (
                f"（较{previous_label} {posts_comparison}）"
                if data.previous_sample_available
                else "（上期样本未知，未作比较）"
            ),
            f"- 评论：{data.overview.comments.current}"
            + (
                f"（较{previous_label} {comments_comparison}）"
                if data.previous_sample_available
                else "（上期样本未知，未作比较）"
            ),
            f"- 平台分布：{_distribution(data.overview.platform_distribution)}",
            "- 情感分布："
            + "、".join(
                f"{_SENTIMENT_LABELS[sentiment]} {data.overview.sentiment_distribution[sentiment]}"
                for sentiment in (
                    ReportSentiment.POSITIVE,
                    ReportSentiment.NEUTRAL,
                    ReportSentiment.NEGATIVE,
                )
            ),
        ]
    )
    lines = [
        f"# {_inline(data.topic_name)} {label}",
        "",
        window_label,
        f"> 截止时间：{_local_minute(data.cutoff_at)}（Asia/Shanghai）",
        f"> 生成方式：{'模型版' if data.narratives else '模板版'}",
        "",
        "## 本周概览" if weekly else "## 今日概览",
        "",
        *_narrative(data, "overview"),
        *overview_lines,
        "",
        "## 重点内容 Top 10",
        "",
        *_narrative(data, "top_content"),
    ]
    if not data.top_contents:
        lines.append("- 本时间窗暂无已分析的相关内容")
    for index, item in enumerate(data.top_contents, start=1):
        interaction = item.interaction_count if item.interaction_count is not None else "未知"
        lines.extend(
            (
                f"{index}. [{item.citation}] {_link(item.title, item.url)}",
                f"   - 平台：{item.source_key}；"
                f"情感：{_SENTIMENT_LABELS[item.sentiment]}；"
                f"互动量：{interaction}"
                + ("（仅已知指标合计）" if len(item.interaction_fields) < 4 else ""),
                f"   - 摘要：{_inline(item.summary)}",
            )
        )
        if item.representative_comments:
            lines.append("   - 代表评论：")
            lines.extend(
                f"     - {_inline(comment.text)}" for comment in item.representative_comments
            )

    lines.extend(("", "## 风险提示", "", *_narrative(data, "risks")))
    if data.risks:
        lines.extend(
            f"- [{item.citation}] {_link(item.title, item.url)}："
            f"{_inline(item.reason)}（互动量 {item.interaction_count}）"
            for item in data.risks
        )
    else:
        lines.append(
            "- 风险尚待分析。" if pending_without_analysis else "- 本时间窗暂无负面高互动内容"
        )

    lines.extend(("", "## 值得关注的声音", "", *_narrative(data, "voices")))
    if data.voices:
        lines.extend(
            f"- [{item.citation}] “{_inline(item.excerpt)}” — {_link('原帖', item.url)}"
            for item in data.voices
        )
    else:
        lines.append("- 本时间窗暂无可展示的代表声音")

    metric_labels = {
        "like_count": "点赞",
        "comment_count": "来源评论计数",
        "repost_count": "转发",
        "view_count": "浏览",
        "play_count": "播放",
        "danmaku_count": "弹幕",
    }
    relation_labels = {
        "root": "根评论",
        "observed": "父评论已采集",
        "unavailable": "父评论不可用",
        "unresolved": "父评论尚未采集",
    }
    if data.pending_contents:
        lines.extend(
            ("", "## 未分析材料", "", "以下材料尚未完成分析，不计入相关性或情感统计。", "")
        )
        for pending in data.pending_contents:
            basis = "发布时间" if pending.time_basis == "published" else "首次发现时间"
            lines.extend(
                (
                    f"- [{pending.citation}] {_link(pending.title, pending.url)}",
                    f"  - 来源：{pending.source_key}；"
                    f"{basis}：{_local_minute(pending.occurred_at)}",
                    "  - 已知指标："
                    + (
                        "、".join(
                            f"{metric_labels[field]} {getattr(pending.metrics, field)}"
                            for field in type(pending.metrics).model_fields
                            if getattr(pending.metrics, field) is not None
                        )
                        or "未知"
                    ),
                )
            )
            for comment in pending.comments:
                comment_label = "评论 " + (comment.native_id or "")
                relation = relation_labels.get(comment.parent_relation_status, "关系未知")
                lines.append(
                    f"  - {_link(comment_label, comment.url)}："
                    f"{_inline(comment.text)}（{relation}）"
                )
    if weekly:
        lines.extend(("", "## 日报版本与核对", ""))
        lines.extend(
            f"- {reference.day.isoformat()}：第 {reference.version} 版 "
            f"；相关帖子 {reference.posts}，评论 {reference.comments}"
            for reference in data.daily_reports
        )
        lines.append(
            "- 缺失日报日期："
            + ("、".join(day.isoformat() for day in data.missing_daily_dates) or "无")
        )
        lines.append(
            "- 周报与日报合计核对："
            + (
                "一致"
                if data.daily_totals_match is True
                else "存在差异；以各自冻结材料为准"
                if data.daily_totals_match is False
                else "日报缺失，暂无法核对"
            )
        )
    if data.coverage.comments:
        labels = {
            "unknown": "采集范围未知",
            "unsupported": "来源不支持",
            "not_authorized": "尚未授权",
            "not_attempted": "尚未采集",
            "failed": "采集失败",
            "partial": "部分采集",
            "observed": "已有采样",
        }
        lines.extend(("", "## 评论采样说明", ""))
        for index, scope in enumerate(data.coverage.comments, start=1):
            lines.append(
                f"- 第 {index} 项 · {scope.source_key}：{labels[scope.status]}；"
                f"已存样本 {scope.stored_comments}，父节点缺口 {scope.unresolved_relations}。"
                f"{scope.note}"
            )
    lines.extend(("", "## 数据覆盖说明", ""))
    for source in data.coverage.sources:
        lines.append(
            f"- {source.source_key}：{_COVERAGE_LABELS[source.status]}"
            f"（成功 {source.succeeded_jobs}，部分成功 {source.partial_jobs}，"
            f"失败 {source.failed_jobs}，进行中 {source.incomplete_jobs}）"
        )
    if not data.coverage.sources:
        lines.append("- 来源采集：无已配置来源")
    lines.extend(
        (
            f"- 按发现时间计入：{data.coverage.discovered_at_count} 条",
            f"- 未分析：{data.coverage.unanalyzed_count} 条",
            "- 概览仅统计已分析且相关的帖子及其评论，未分析材料单独列出。",
            "- 未分析材料每帖最多展示 50 条评论摘录，已存样本量见采样说明。",
            f"- {data.coverage.disclaimer}",
            "",
        )
    )
    return "\n".join(lines)
