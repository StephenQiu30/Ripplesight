from fastapi import APIRouter

from api.routers.ai_models import router as ai_models_router
from api.routers.codex_resets import router as codex_resets_router
from api.routers.collection_coverage import router as collection_coverage_router
from api.routers.collection_jobs import router as collection_jobs_router
from api.routers.content_records import router as content_records_router
from api.routers.editorial import router as editorial_router
from api.routers.editorial_sources import router as editorial_sources_router
from api.routers.events import router as events_router
from api.routers.health import router as health_router
from api.routers.hotlists import router as hotlists_router
from api.routers.leaderboard import router as leaderboard_router
from api.routers.monitor_topics import router as monitor_topics_router
from api.routers.operations import feedback_router
from api.routers.operations import router as operations_router
from api.routers.publication import router as publication_router
from api.routers.publication_editions import router as publication_editions_router
from api.routers.publication_media import router as publication_media_router
from api.routers.report_editions import router as report_editions_router
from api.routers.reports import router as reports_router
from api.routers.site import router as site_router
from api.routers.source_capabilities import router as source_capabilities_router
from api.routers.source_connections import router as source_connections_router
from api.routers.translations import router as translations_router

api_router = APIRouter(prefix="/api")
api_router.include_router(ai_models_router)
api_router.include_router(health_router)
api_router.include_router(hotlists_router)
api_router.include_router(collection_jobs_router)
api_router.include_router(collection_coverage_router)
api_router.include_router(content_records_router)
api_router.include_router(editorial_router)
api_router.include_router(editorial_sources_router)
api_router.include_router(translations_router)
api_router.include_router(events_router)
api_router.include_router(leaderboard_router)
api_router.include_router(codex_resets_router)
api_router.include_router(monitor_topics_router)
api_router.include_router(operations_router)
api_router.include_router(feedback_router)
api_router.include_router(reports_router)
api_router.include_router(report_editions_router)
api_router.include_router(publication_router)
api_router.include_router(publication_editions_router)
api_router.include_router(publication_media_router)
api_router.include_router(site_router)
api_router.include_router(source_capabilities_router)
api_router.include_router(source_connections_router)
