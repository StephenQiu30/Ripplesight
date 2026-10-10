"""Register runtime mappings; sql/schema.sql owns DDL."""

import ai.capability_models as _ai_capability_models  # noqa: F401
import ai.models as _ai_models  # noqa: F401
import analysis.editorial_models as _analysis_editorial_models  # noqa: F401
import analysis.evaluation_models as _analysis_evaluation_models  # noqa: F401
import analysis.models as _analysis_models  # noqa: F401
import analysis.translation_models as _analysis_translation_models  # noqa: F401
import connections.editorial_icon_models as _connections_editorial_icon_models  # noqa: F401
import connections.editorial_models as _connections_editorial_models  # noqa: F401
import connections.models as _connections_models  # noqa: F401
import content.editorial_rendered_models as _content_editorial_rendered_models  # noqa: F401
import content.models as _content_models  # noqa: F401
import events.embedding_models as _events_embedding_models  # noqa: F401
import events.fact_models as _events_fact_models  # noqa: F401
import events.heat_models as _events_heat_models  # noqa: F401
import events.models as _events_models  # noqa: F401
import events.story_models as _events_story_models  # noqa: F401
import evidence.models as _evidence_models  # noqa: F401
import identity.models as _identity_models  # noqa: F401
import jobs.models as _jobs_models  # noqa: F401
import knowledge.models as _knowledge_models  # noqa: F401
import leaderboard.models as _leaderboard_models  # noqa: F401
import monitors.codex_models as _monitors_codex_models  # noqa: F401
import monitors.models as _monitors_models  # noqa: F401
import notifications.alert_models as _notifications_alert_models  # noqa: F401
import notifications.models as _notifications_models  # noqa: F401
import operations.models as _operations_models  # noqa: F401
import operations.site_models as _operations_site_models  # noqa: F401
import publication.media_mirror_models as _publication_media_mirror_models  # noqa: F401
import publication.publication_models as _publication_publication_models  # noqa: F401
import reports.edition_models as _reports_edition_models  # noqa: F401
import reports.export_models as _reports_export_models  # noqa: F401
import reports.models as _reports_models  # noqa: F401
from db.base import Base as Base

metadata = Base.metadata

__all__ = ["Base", "metadata"]
