from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from backend.core.application import (
    DigestDeliveryWorkflowService,
    DigestRenderService,
    DigestService,
    HotspotDiscoveryService,
)
from backend.core.infrastructure import (
    InMemoryDailyDigestRepository,
    InMemoryDigestDeliveryGateway,
    InMemoryRawContentItemRepository,
    InMemoryHotspotEventRepository,
    InMemorySourceConfigRepository,
)
from services.bootstrap_data import build_digest_recipients, build_raw_records, build_source_configs, default_ingested_at


@dataclass(frozen=True, slots=True)
class WorkerContainer:
    workflow_service: DigestDeliveryWorkflowService
    delivery_gateway: InMemoryDigestDeliveryGateway
    default_recipient: str


@lru_cache(maxsize=1)
def get_worker_container() -> WorkerContainer:
    source_repository = InMemorySourceConfigRepository(build_source_configs())
    hotspot_event_repository = InMemoryHotspotEventRepository()
    raw_content_repository = InMemoryRawContentItemRepository()
    digest_repository = InMemoryDailyDigestRepository()
    delivery_gateway = InMemoryDigestDeliveryGateway()

    hotspot_service = HotspotDiscoveryService(
        source_repository=source_repository,
        hotspot_event_repository=hotspot_event_repository,
        raw_content_repository=raw_content_repository,
    )
    ingested_at = default_ingested_at()
    raw_items = hotspot_service.collect_raw_items(build_raw_records(), ingested_at=ingested_at)
    hotspot_service.build_hotspot_events(raw_items)

    digest_service = DigestService(
        hotspot_event_repository=hotspot_event_repository,
        daily_digest_repository=digest_repository,
    )
    render_service = DigestRenderService(hotspot_event_repository)
    workflow_service = DigestDeliveryWorkflowService(
        digest_service=digest_service,
        digest_repository=digest_repository,
        digest_render_service=render_service,
        delivery_gateway=delivery_gateway,
    )
    default_recipient = os.getenv("RESEND_TO_EMAIL", build_digest_recipients()[0])
    return WorkerContainer(
        workflow_service=workflow_service,
        delivery_gateway=delivery_gateway,
        default_recipient=default_recipient,
    )
