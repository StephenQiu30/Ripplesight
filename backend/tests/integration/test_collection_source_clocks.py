# ruff: noqa: F811
from datetime import timedelta

from sqlalchemy import select
from tests.integration.test_hotlist_persistence import (
    _accept,
    _execute,
    _executor,
    _message,
    _page,
    runtime,  # noqa: F401
)
from tests.integration.test_webpage_persistence import (
    SuccessfulDocumentAdapter,
    _accept_webpage_job,
    _enable_firecrawl_budget,
    webpage_context,  # noqa: F401
)

from content.collection import WebPageCollectionExecutor
from content.event_reading import load_event_member_content_in_transaction
from content.schemas import EventContentReadReference
from events.heat import EventHeatService
from events.heat_models import EventAttentionSource
from events.heat_schemas import AttentionSourceInput
from jobs.execution import JobExecutionService
from jobs.schemas import JobAcceptedMessage
from jobs.source_scopes import (
    collection_selector_reference,
    load_collection_source_scopes_in_transaction,
)


def test_completed_empty_hotlist_advances_exact_clock_and_checkpoint_replay_does_not(runtime):
    at = runtime.due_at + timedelta(minutes=2)
    with runtime.sessions() as session:
        service = EventHeatService(session, clock=lambda: runtime.due_at)
        for kind, reference in (
            ("source", "hotlist_weibo"),
            ("native_scope", "hotlist:hotlist_weibo"),
            ("author", "another-author"),
        ):
            service.upsert_source(
                owner_id=runtime.owner_id,
                command=AttentionSourceInput(
                    source_key="hotlist_weibo",
                    selector_kind=kind,
                    selector_ref=reference,
                    name=reference,
                    mode="editorial",
                ),
            )
    job_id = _accept(runtime, runtime.due_at)
    lease = _execute(runtime, job_id, _page(at))
    _executor(runtime, _page(at + timedelta(minutes=1))).execute(_message(runtime, job_id), lease)
    with runtime.sessions() as session:
        clocks = {
            row.selector_kind: row.last_successful_fetch_at
            for row in session.scalars(select(EventAttentionSource))
        }
    assert clocks == {"source": None, "native_scope": at, "author": None}


def test_webpage_clock_and_exact_event_scope_use_original_job_not_content_identity(webpage_context):
    context = webpage_context
    _enable_firecrawl_budget(context)
    clock = [context.now + timedelta(seconds=2)]
    job_id, raw_message = _accept_webpage_job(context, clock=clock)
    message = JobAcceptedMessage.model_validate_json(raw_message.value())
    with context.sessions() as session, session.begin():
        scope = load_collection_source_scopes_in_transaction(
            session, owner_id=context.owner_id, job_ids=(job_id,)
        )[job_id]
    with context.sessions() as session:
        source = EventHeatService(session, clock=lambda: clock[0]).upsert_source(
            owner_id=context.owner_id,
            command=AttentionSourceInput(
                source_key="web",
                selector_kind="native_scope",
                selector_ref=scope.selector_ref,
                name="受控单页",
                mode="editorial",
            ),
        )
        lease = JobExecutionService(session, lease_seconds=60, clock=lambda: clock[0]).acquire(
            job_id=job_id, worker_id="exact-scope-worker"
        )
    adapter = SuccessfulDocumentAdapter(clock)
    executor = WebPageCollectionExecutor(
        context.sessions,
        lease_seconds=60,
        adapter_factory=lambda _hosts: adapter,
        clock=lambda: clock[0],
    )
    saved = executor.execute(message, lease)
    clock[0] += timedelta(seconds=5)
    executor.execute(message, saved)
    with context.sessions() as session, session.begin():
        assert session.get(EventAttentionSource, source.id).last_successful_fetch_at == clock[
            0
        ] - timedelta(seconds=5)
        from content.models import ContentRecord, ContentVersion

        record = session.scalar(select(ContentRecord))
        version = session.scalar(select(ContentVersion))
        reference = EventContentReadReference(record.id, version.id, None)
        view = load_event_member_content_in_transaction(
            session, owner_id=context.owner_id, references=(reference,), now=clock[0]
        )[reference]
        assert view.native_scope == record.native_scope == "example.com"
        assert view.collection_scope == scope.selector_ref
        assert view.collection_scope == collection_selector_reference(
            "webpage.collect", "web", {"target_url": adapter.requests[0].url}
        )
