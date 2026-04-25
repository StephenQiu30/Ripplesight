from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.app.db.session import get_session
from apps.api.app.models.daily_report import DailyReport
from apps.api.app.schemas.daily_report import DailyReportCreate, DailyReportRead
from apps.api.app.services.daily_digest import generate_daily_report, send_daily_report

router = APIRouter(prefix="/api/daily-reports", tags=["daily-reports"])


@router.post("", response_model=DailyReportRead, status_code=201)
def create_daily_report(payload: DailyReportCreate, session: Session = Depends(get_session)) -> DailyReport:
    report = generate_daily_report(session, report_date=payload.report_date)
    session.commit()
    session.refresh(report)
    return report


@router.post("/{report_id}/send", response_model=DailyReportRead)
def send_report(report_id: int, session: Session = Depends(get_session)) -> DailyReport:
    report = session.get(DailyReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Daily report not found.")
    send_daily_report(session, report)
    session.commit()
    session.refresh(report)
    return report


@router.get("", response_model=dict)
def list_daily_reports(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    reports = list(session.scalars(select(DailyReport).order_by(DailyReport.report_date.desc()).limit(limit).offset(offset)))
    return {"items": [DailyReportRead.model_validate(report).model_dump(mode="json") for report in reports], "limit": limit, "offset": offset}


@router.get("/{report_id}", response_model=DailyReportRead)
def get_daily_report(report_id: int, session: Session = Depends(get_session)) -> DailyReport:
    report = session.get(DailyReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Daily report not found.")
    return report
