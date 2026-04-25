from __future__ import annotations

from dataclasses import replace

import unittest

from backend.core.application import DigestDeliveryWorkflowService, DigestRenderService, DigestService
from backend.core.domain import HotspotEvent
from backend.core.infrastructure import (
    InMemoryDailyDigestRepository,
    InMemoryDigestDeliveryGateway,
    InMemoryHotspotEventRepository,
)
try:
    from services.worker.app import celery_app
    from services.worker.bootstrap import get_worker_container
except ModuleNotFoundError as exc:  # pragma: no cover - local host may not have Celery installed
    celery_app = None
    get_worker_container = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(IMPORT_ERROR is not None, f"Celery not installed in current environment: {IMPORT_ERROR}")
class WorkerDigestDeliveryTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert celery_app is not None
        celery_app.conf.broker_url = "memory://"
        celery_app.conf.result_backend = "cache+memory://"
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_store_eager_result = True
        celery_app.__dict__.pop("_backend", None)

    def setUp(self) -> None:
        assert get_worker_container is not None
        get_worker_container.cache_clear()

    def test_digest_delivery_task_updates_status_and_sends_email(self) -> None:
        task = celery_app.tasks["worker.generate_and_deliver_daily_digest"]
        result = task.run(recipient="ops@example.com")
        container = get_worker_container()

        self.assertEqual("delivered", result["delivery_status"])
        self.assertEqual(1, len(container.delivery_gateway.sent_emails))
        self.assertEqual("ops@example.com", container.delivery_gateway.sent_emails[0].recipient)

    def test_rendered_email_contains_digest_title(self) -> None:
        container = get_worker_container()
        delivered_digest, _ = container.workflow_service.generate_and_deliver(recipient="ops@example.com")
        email = container.delivery_gateway.sent_emails[0]

        self.assertIn(delivered_digest.title, email.subject)
        self.assertIn("今日摘要：", email.body)

    def test_rendered_email_contains_event_summary_and_evidence(self) -> None:
        container = get_worker_container()
        digest = container.workflow_service._digest_service.get_today_digest()
        rendered, is_partial = container.workflow_service._digest_render_service.render_digest_email(digest, recipient="ops@example.com")
        first_event = next(iter(container.workflow_service._digest_render_service._hotspot_event_repository.list_all()))
        self.assertFalse(is_partial)
        self.assertIn(first_event.event_title, rendered.body)
        self.assertIn("摘要：", rendered.body)
        if first_event.evidence_links:
            self.assertIn(first_event.evidence_links[0].url, rendered.body)

    def test_rendering_degradation_keeps_delivery_trackable(self) -> None:
        base_events = list(get_worker_container().workflow_service._digest_render_service._hotspot_event_repository.list_all())
        bad_event = replace(base_events[0], id="event-bad", evidence_links=(object(),))
        events = [bad_event, *base_events[1:]]
        workflow = self._build_workflow_with_events(events)

        delivered_digest, _ = workflow.generate_and_deliver(recipient="ops@example.com")

        self.assertEqual("partial", delivered_digest.delivery_status)
        self.assertIn("降级说明", workflow._delivery_gateway.sent_emails[0].body)

    def test_rendering_failure_uses_minimal_fallback_but_updates_status(self) -> None:
        workflow = self._build_workflow_with_events(
            list(get_worker_container().workflow_service._digest_render_service._hotspot_event_repository.list_all())
        )
        original_renderer = workflow._digest_render_service.render_digest_email

        def always_fail(*args, **kwargs):
            del args
            del kwargs
            raise RuntimeError("render failure")

        workflow._digest_render_service.render_digest_email = always_fail
        delivered_digest, _ = workflow.generate_and_deliver(recipient="ops@example.com")
        workflow._digest_render_service.render_digest_email = original_renderer

        self.assertEqual("partial", delivered_digest.delivery_status)
        self.assertIn("降级", workflow._delivery_gateway.sent_emails[0].subject)

    def _build_workflow_with_events(self, events: list[HotspotEvent]) -> DigestDeliveryWorkflowService:
        repository = InMemoryHotspotEventRepository(events)
        digest_repository = InMemoryDailyDigestRepository()
        delivery_gateway = InMemoryDigestDeliveryGateway()
        digest_service = DigestService(
            hotspot_event_repository=repository,
            daily_digest_repository=digest_repository,
        )
        render_service = DigestRenderService(repository)
        return DigestDeliveryWorkflowService(
            digest_service=digest_service,
            digest_repository=digest_repository,
            digest_render_service=render_service,
            delivery_gateway=delivery_gateway,
        )


if __name__ == "__main__":
    unittest.main()
