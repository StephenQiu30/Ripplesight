"""Weekly report content from typed domain aggregates, never from foreign ORM."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from content.operations_reading import IngestionHealth


@dataclass(frozen=True, slots=True)
class WeeklySource:
    source_key: str
    name: str
    kind: str
    enabled: bool
    created_at: datetime
    health: str
    consecutive_failures: int
    last_success_at: datetime | None
    last_error: str | None


def source_health_report(
    *,
    now: datetime,
    sources: tuple[WeeklySource, ...],
    ingestion: IngestionHealth,
    selected_current: int,
    selected_previous: int,
) -> tuple[str, dict[str, object]]:
    since = now - timedelta(days=7)
    received = {item.source_key: item for item in ingestion.sources}
    current = sum(item.current_count for item in ingestion.sources)
    previous = sum(item.previous_count for item in ingestion.sources)
    change = f"{(current - previous) / previous:+.0%}" if previous else "—"
    enabled = [item for item in sources if item.enabled]
    failing = [item for item in enabled if item.health == "failing"]
    degraded = [item for item in enabled if item.health == "degraded"]
    added = [item for item in sources if item.created_at >= since]
    silent = [
        item
        for item in enabled
        if item.created_at < since
        and item.health != "failing"
        and item.kind not in {"external", "mp_account"}
        and (item.source_key not in received or received[item.source_key].last_received_at < since)
    ]
    lines = [
        f"本周收录 {current} 条(上周 {previous},{change})。",
        f"本周收录内容中当前发布精选 {selected_current} 条(上周收录中 {selected_previous} 条)。",
        f"在用来源 {len(enabled)} 个,本周新增 {len(added)} 个;"
        f"抓取失败 {len(failing)} 个,降级 {len(degraded)} 个。",
    ]
    if failing:
        lines.extend(
            [
                "",
                "抓取失败的来源:",
                *(
                    f"· {item.name}:连续失败 {item.consecutive_failures} 次;"
                    "最近成功 "
                    + (item.last_success_at.isoformat() if item.last_success_at else "尚未成功")
                    + ";"
                    f"{item.last_error or '无错误代码'}"
                    for item in failing[:10]
                ),
            ]
        )
    if silent:
        lines.extend(
            [
                "",
                "7 天没有新内容的来源:",
                *(
                    f"· {item.name}:"
                    + (
                        received[item.source_key].last_received_at.isoformat()
                        if item.source_key in received
                        else "从未收录"
                    )
                    for item in silent[:15]
                ),
            ]
        )
    lines.extend(
        ["", "请在运营页检查来源与运行记录。" if failing or silent else "没有需要处理的来源。"]
    )
    return "\n".join(lines), {
        "window_start": since.isoformat(),
        "previous_window_start": (since - timedelta(days=7)).isoformat(),
        "window_end": now.isoformat(),
        "collected_current": current,
        "collected_previous": previous,
        "selected_current": selected_current,
        "selected_previous": selected_previous,
        "enabled_sources": len(enabled),
        "added_sources": len(added),
        "failing_sources": len(failing),
        "degraded_sources": len(degraded),
        "silent_sources": [item.source_key for item in silent],
    }
