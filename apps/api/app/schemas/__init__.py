"""Pydantic schemas will be introduced by the execution plans."""
from apps.api.app.schemas.ai_analysis import AiAnalysisRead
from apps.api.app.schemas.check_run import CheckRunCreate, CheckRunRead
from apps.api.app.schemas.daily_report import DailyReportCreate, DailyReportRead
from apps.api.app.schemas.hotspot import HotspotRead
from apps.api.app.schemas.keyword import KeywordCreate, KeywordRead, KeywordUpdate
from apps.api.app.schemas.notification import NotificationRead
from apps.api.app.schemas.search import SearchCreate, SearchRead, SearchResultRead
from apps.api.app.schemas.setting import SettingRead, SettingUpsert
from apps.api.app.schemas.source import SourceCreate, SourceRead, SourceUpdate

__all__ = [
    "AiAnalysisRead",
    "CheckRunCreate",
    "CheckRunRead",
    "DailyReportCreate",
    "DailyReportRead",
    "HotspotRead",
    "KeywordCreate",
    "KeywordRead",
    "KeywordUpdate",
    "NotificationRead",
    "SearchCreate",
    "SearchRead",
    "SearchResultRead",
    "SettingRead",
    "SettingUpsert",
    "SourceCreate",
    "SourceRead",
    "SourceUpdate",
]
