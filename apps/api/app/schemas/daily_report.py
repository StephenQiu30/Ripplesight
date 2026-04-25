from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class DailyReportCreate(BaseModel):
    report_date: date | None = None


class DailyReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_date: date
    status: str
    subject: str
    summary: str | None
    content: str
    hotspot_count: int
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
