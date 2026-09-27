from __future__ import annotations

import os
import time
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from confluent_kafka import Consumer, KafkaError, Message, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from fastapi.testclient import TestClient
from sqlalchemy import text
from tests.integration.test_comment_runs_http import _seed_old_hn_post
from tests.integration.test_monitor_topics import _csrf_headers
from tests.integration.test_topic_runs import monitor_topic_client as _topic_client  # noqa: F401

from content.comments_execution import CommentsExecutor
from jobs.execution import JobCompletion
from jobs.services import OutboxEnvelope
from sources.adapters.hackernews import HackerNewsAdapter
from worker.app import JobExecutionContext, create_job_message_handler
from worker.messaging import MessageHandler, process_message, publish_outbox


def test_manual_comments_kafka_redelivery_keeps_threads_budget_and_offset(
    request: pytest.FixtureRequest,
) -> None:
    bootstrap = os.getenv("HOTKEY_TEST_KAFKA_BOOTSTRAP_SERVERS")
    if bootstrap is None:
        pytest.skip("HOTKEY_TEST_KAFKA_BOOTSTRAP_SERVERS is required")
    client: TestClient = request.getfixturevalue("_topic_client")
    content_id = _seed_old_hn_post(client)
    accepted = client.post(
        f"/api/contents/{content_id}/comment-runs",
        headers=_csrf_headers(client),
        json={"operation_id": str(uuid4())},
    )
    assert accepted.status_code == 202, accepted.json()
    job_id = UUID(accepted.json()["job_id"])
    sessions = client.app.state.session_factory
    with sessions() as session:
        outbox = session.execute(
            text(
                "SELECT id, topic, message_key, event_type, payload "
                "FROM outbox_messages WHERE aggregate_id = :job_id"
            ),
            {"job_id": job_id},
        ).one()
    topic = f"hotkey.tests.plan038.{uuid4().hex}"
    group = f"hotkey-tests-plan038-{uuid4().hex}"
    admin = AdminClient({"bootstrap.servers": bootstrap})
    producer = Producer({"bootstrap.servers": bootstrap})
    consumers: list[Consumer] = []
    requested: list[str] = []

    def new_consumer() -> Consumer:
        consumer = Consumer(
            {
                "bootstrap.servers": bootstrap,
                "group.id": group,
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
            }
        )
        consumer.subscribe([topic])
        consumers.append(consumer)
        return consumer

    def next_message(consumer: Consumer) -> Message:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            message = consumer.poll(1.0)
            if message is None:
                continue
            error = message.error()
            if error is not None:
                if error.code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                    continue
                raise AssertionError(f"Kafka consumer error: {error.code()}")
            return message
        raise AssertionError("comment Job Kafka message was not delivered")

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        assert request.url.path == "/api/v1/items/123456"
        published = int((datetime.now(UTC) - timedelta(days=2)).timestamp())
        return httpx.Response(
            200,
            json={
                "id": 123456,
                "children": [
                    {
                        "type": "comment",
                        "id": 987011,
                        "author": "hn-reader",
                        "text": "<p>root</p>",
                        "created_at_i": published,
                        "children": [
                            {
                                "type": "comment",
                                "id": 987012,
                                "author": "hn-reply",
                                "text": "<p>reply</p>",
                                "created_at_i": published + 60,
                                "children": [],
                            }
                        ],
                    }
                ],
            },
        )

    def clock() -> datetime:
        return datetime.now(UTC) + timedelta(seconds=1)

    def new_handler() -> MessageHandler:
        executor = CommentsExecutor(
            sessions,
            lease_seconds=75,
            clock=clock,
            adapter_factory=lambda before, cancelled, max_requests, max_seconds: HackerNewsAdapter(
                before_request=before,
                cancelled=cancelled,
                max_requests=max_requests,
                max_seconds=max_seconds,
                transport=httpx.MockTransport(respond),
            ),
        )

        def comments(context: JobExecutionContext) -> JobCompletion:
            context.lease, completion = executor.execute(context.message, context.lease)
            return completion

        return create_job_message_handler(
            sessions,
            {"source.comments": comments},
            worker_id="plan038-kafka-test",
            lease_seconds=75,
            clock=clock,
        )

    try:
        admin.create_topics([NewTopic(topic, 1, 1)])[topic].result(10)
        envelope = replace(
            OutboxEnvelope(
                message_id=outbox.id,
                topic=outbox.topic,
                message_key=outbox.message_key,
                event_type=outbox.event_type,
                schema_version=2,
                payload=outbox.payload,
            ),
            topic=topic,
        )
        publish_outbox(producer, envelope, timeout_seconds=10)
        first_consumer = new_consumer()
        first = next_message(first_consumer)
        new_handler()(first)
        first_consumer.close()  # Simulate a Worker restart before offset commit.
        second_consumer = new_consumer()
        replay = next_message(second_consumer)
        assert (replay.partition(), replay.offset()) == (first.partition(), first.offset())
        partition, offset = replay.partition(), replay.offset()
        assert partition is not None and offset is not None
        process_message(second_consumer, replay, {topic: new_handler()})
        committed = second_consumer.committed([TopicPartition(topic, partition)], 10)
        assert committed[0].offset == offset + 1
        publish_outbox(producer, envelope, timeout_seconds=10)
        duplicate = next_message(second_consumer)
        assert (duplicate.partition(), duplicate.offset()) == (partition, offset + 1)
        process_message(second_consumer, duplicate, {topic: new_handler()})
        committed = second_consumer.committed([TopicPartition(topic, partition)], 10)
        assert committed[0].offset == offset + 2
        assert len(requested) == 1
        with sessions() as session:
            assert session.execute(
                text("SELECT status, requests_sent, items_saved FROM jobs WHERE id = :job_id"),
                {"job_id": job_id},
            ).one() == ("succeeded", 1, 2)
            assert (
                session.scalar(
                    text("SELECT count(*) FROM processed_messages WHERE job_id = :job_id"),
                    {"job_id": job_id},
                )
                == 1
            )
            assert session.execute(
                text(
                    "SELECT c.external_id, root.external_id, parent.external_id, "
                    "target.external_id, t.parent_relation_status "
                    "FROM content_threads t JOIN content_records c ON c.id = t.content_id "
                    "LEFT JOIN content_records root ON root.id = t.root_content_id "
                    "LEFT JOIN content_records parent ON parent.id = t.parent_content_id "
                    "LEFT JOIN content_records target ON target.id = t.reply_target_content_id "
                    "WHERE t.post_content_id = :post_id ORDER BY c.external_id"
                ),
                {"post_id": content_id},
            ).all() == [
                ("987011", "987011", None, None, "root"),
                ("987012", "987011", "987011", "987011", "observed"),
            ]
            assert session.execute(
                text(
                    "SELECT p.budget_key, sum(r.actual_units) FROM resource_budget_reservations r "
                    "JOIN resource_budget_policies p ON p.id = r.budget_policy_id "
                    "GROUP BY p.budget_key ORDER BY p.budget_key"
                )
            ).all() == [
                ("global.plan038.comments.daily", 1),
                ("source.hackernews.network.daily", 1),
            ]
    finally:
        for consumer in consumers:
            consumer.close()
        with suppress(Exception):
            admin.delete_topics([topic], operation_timeout=10)[topic].result(10)
