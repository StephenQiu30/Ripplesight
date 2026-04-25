from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import case, select
from sqlalchemy.orm import Session, selectinload

from apps.api.app.models.ai_analysis import AiAnalysis
from apps.api.app.models.daily_report import DailyReport
from apps.api.app.models.hotspot import Hotspot
from apps.api.app.models.notification import Notification
from apps.api.app.services.notification import notify_daily_report

MAX_DIGEST_ITEMS = 10


def generate_daily_report(session: Session, report_date: date | None = None) -> DailyReport:
    target_date = report_date or datetime.now(timezone.utc).date()
    hotspots = _load_digest_hotspots(session, target_date)
    subject = f"AI 热点日报 - {target_date.isoformat()}"
    summary, content = _render_digest(target_date, hotspots)

    report = session.scalar(select(DailyReport).where(DailyReport.report_date == target_date))
    if report is None:
        report = DailyReport(report_date=target_date, subject=subject, summary=summary, content=content)
        session.add(report)
    else:
        report.subject = subject
        report.summary = summary
        report.content = content
        report.status = "generated"
        report.sent_at = None
    report.hotspot_count = len(hotspots)
    session.flush()
    session.refresh(report)
    return report


def send_daily_report(session: Session, report: DailyReport) -> Notification:
    notification = notify_daily_report(session, report)
    if notification.status == "sent":
        report.status = "sent"
        report.sent_at = notification.sent_at
    elif notification.status == "failed":
        report.status = "failed"
    else:
        report.status = "skipped"
    session.flush()
    session.refresh(report)
    return notification


def generate_and_send_daily_report(session: Session, report_date: date | None = None) -> DailyReport:
    report = generate_daily_report(session, report_date=report_date)
    send_daily_report(session, report)
    return report


def _load_digest_hotspots(session: Session, report_date: date) -> list[Hotspot]:
    start = datetime.combine(report_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    importance_rank = case(
        (AiAnalysis.importance == "high", 3),
        (AiAnalysis.importance == "medium", 2),
        (AiAnalysis.importance == "low", 1),
        else_=0,
    )
    stmt = (
        select(Hotspot)
        .join(AiAnalysis, AiAnalysis.hotspot_id == Hotspot.id)
        .options(selectinload(Hotspot.source), selectinload(Hotspot.keyword), selectinload(Hotspot.ai_analysis))
        .where(Hotspot.fetched_at >= start, Hotspot.fetched_at < end)
        .order_by(importance_rank.desc(), AiAnalysis.relevance_score.desc(), Hotspot.fetched_at.desc())
        .limit(MAX_DIGEST_ITEMS)
    )
    return list(session.scalars(stmt).unique())


def _render_digest(report_date: date, hotspots: list[Hotspot]) -> tuple[str, str]:
    if not hotspots:
        summary = "今日没有发现符合条件的 AI 热点。"
        content = "\n".join(
            [
                f"# AI 热点日报 - {report_date.isoformat()}",
                "",
                summary,
            ]
        )
        return summary, content

    high_count = sum(1 for hotspot in hotspots if hotspot.ai_analysis and hotspot.ai_analysis.importance == "high")
    summary = f"今日共筛选出 {len(hotspots)} 条 AI 热点，其中高重要性 {high_count} 条。"
    lines = [
        f"# AI 热点日报 - {report_date.isoformat()}",
        "",
        summary,
        "",
        "## Top 热点",
    ]
    for index, hotspot in enumerate(hotspots, start=1):
        analysis = hotspot.ai_analysis
        source_name = hotspot.source.name if hotspot.source else "Unknown source"
        keyword = hotspot.keyword.keyword if hotspot.keyword else "未关联关键词"
        lines.extend(
            [
                "",
                f"{index}. {hotspot.title}",
                f"   - 来源：{source_name}",
                f"   - 关键词：{keyword}",
                f"   - 重要性：{analysis.importance if analysis else 'unknown'}",
                f"   - 相关性：{analysis.relevance_score if analysis else 0}",
                f"   - 摘要：{analysis.summary if analysis and analysis.summary else hotspot.snippet or ''}",
                f"   - 理由：{analysis.relevance_reason if analysis and analysis.relevance_reason else ''}",
                f"   - 链接：{hotspot.url}",
            ]
        )
    return summary, "\n".join(lines)
