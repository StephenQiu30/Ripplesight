from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta, timezone

from apps.api.app.core.settings import settings
from apps.api.app.db.session import SessionLocal
from apps.api.app.services.daily_digest import generate_and_send_daily_report
from apps.api.app.services.check_runner import run_hotspot_check

_last_digest_date = None


async def scheduler_loop() -> None:
    while True:
        await asyncio.sleep(max(settings.check_interval_minutes, 1) * 60)
        await asyncio.to_thread(_run_scheduled_check)


def start_scheduler() -> asyncio.Task | None:
    if not settings.scheduler_enabled:
        return None
    return asyncio.create_task(scheduler_loop())


async def stop_scheduler(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _run_scheduled_check() -> None:
    with SessionLocal() as session:
        run_hotspot_check(session, trigger_type="scheduled")
        _maybe_run_daily_digest(session)


def _maybe_run_daily_digest(session) -> None:
    global _last_digest_date
    if not settings.daily_digest_enabled:
        return
    now = datetime.now(timezone.utc)
    if now.hour < settings.daily_digest_hour:
        return
    report_date = now.date() - timedelta(days=1)
    if _last_digest_date == report_date:
        return
    generate_and_send_daily_report(session, report_date=report_date)
    session.commit()
    _last_digest_date = report_date
