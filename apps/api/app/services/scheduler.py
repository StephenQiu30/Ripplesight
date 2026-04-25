from __future__ import annotations

import asyncio
from contextlib import suppress

from apps.api.app.core.settings import settings
from apps.api.app.db.session import SessionLocal
from apps.api.app.services.check_runner import run_hotspot_check


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
