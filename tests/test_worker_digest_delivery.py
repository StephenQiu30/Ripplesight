from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
