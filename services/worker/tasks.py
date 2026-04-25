from __future__ import annotations

from services.worker.app import celery_app
from services.worker.bootstrap import get_worker_container


@celery_app.task(name="worker.generate_and_deliver_daily_digest")
def generate_and_deliver_daily_digest(recipient: str | None = None) -> dict[str, str]:
    container = get_worker_container()
    delivered_digest, receipt = container.workflow_service.generate_and_deliver(
        recipient=recipient or container.default_recipient,
    )
    return {
        "digest_id": delivered_digest.id,
        "delivery_status": delivered_digest.delivery_status,
        "message_id": receipt.message_id,
    }
