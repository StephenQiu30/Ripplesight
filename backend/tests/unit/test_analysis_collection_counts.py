from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from analysis.services import AnalysisService
from jobs.schemas import JobStatus


class AnnotationSession:
    def __init__(self, rows: list[tuple[UUID, int, UUID, str, str]]) -> None:
        self.rows = rows
        self.queries: list[Any] = []

    def in_transaction(self) -> bool:
        return True

    def execute(self, query: object) -> SimpleNamespace:
        self.queries.append(query)
        return SimpleNamespace(all=lambda: self.rows)


def _job(
    *,
    topic_id: UUID,
    rule_version: int,
    prompt_version: str,
    version_ids: tuple[UUID, ...],
    status: JobStatus,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        scope={
            "topic_id": str(topic_id),
            "topic_rule_version": rule_version,
            "prompt_version": prompt_version,
            "content_version_ids": json.dumps([str(version_id) for version_id in version_ids]),
        },
    )


def test_collection_analysis_counts_batch_preserves_priority_and_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, topic_id = uuid4(), uuid4()
    collection_jobs = [uuid4() for _ in range(5)]
    valid, invalid, row_pending, job_failed, job_pending, ambiguous, missing = (
        uuid4() for _ in range(7)
    )
    session = AnnotationSession(
        [
            (topic_id, 2, valid, "frozen-v1", "valid"),
            (topic_id, 2, invalid, "frozen-v1", "invalid"),
            (topic_id, 2, row_pending, "frozen-v1", "pending"),
        ]
    )
    context = SimpleNamespace(configuration_ref=f"topic:{topic_id}", configuration_version=2)
    seen_contexts: list[tuple[UUID, set[UUID]]] = []

    def contexts(_session: object, *, owner_id: UUID, job_ids: set[UUID]) -> dict[UUID, object]:
        seen_contexts.append((owner_id, job_ids))
        return {job_id: context for job_id in collection_jobs[:4]}

    analysis_jobs = (
        _job(
            topic_id=topic_id,
            rule_version=2,
            prompt_version="frozen-v1",
            version_ids=(valid, invalid, row_pending, job_failed),
            status=JobStatus.FAILED,
        ),
        _job(
            topic_id=topic_id,
            rule_version=2,
            prompt_version="frozen-v1",
            version_ids=(job_pending,),
            status=JobStatus.RUNNING,
        ),
        _job(
            topic_id=topic_id,
            rule_version=2,
            prompt_version="frozen-v1",
            version_ids=(ambiguous,),
            status=JobStatus.QUEUED,
        ),
        _job(
            topic_id=topic_id,
            rule_version=2,
            prompt_version="frozen-v2",
            version_ids=(ambiguous,),
            status=JobStatus.QUEUED,
        ),
    )
    job_reads: list[UUID] = []

    class JobsDomain:
        def __init__(self, _session: object) -> None:
            pass

        def list_analysis_jobs_in_transaction(
            self, *, owner_id: UUID, topic_ids: set[UUID] | None = None
        ) -> tuple[object, ...]:
            job_reads.append(owner_id)
            assert topic_ids == {topic_id}
            return analysis_jobs

    monkeypatch.setattr("analysis.services.load_content_job_contexts", contexts)
    monkeypatch.setattr("analysis.services.CollectionDueWindowService", JobsDomain)

    counts = AnalysisService(cast(Session, session)).collection_analysis_counts_in_transaction(
        owner_id=owner_id,
        targets_by_job={
            collection_jobs[0]: (
                topic_id,
                2,
                (valid, invalid, row_pending, job_failed, job_pending),
            ),
            collection_jobs[1]: (topic_id, 2, (ambiguous,)),
            collection_jobs[2]: (topic_id, 2, (valid, missing)),
            collection_jobs[3]: (topic_id, 2, ()),
            collection_jobs[4]: (topic_id, 2, (valid,)),
        },
    )

    first = counts[collection_jobs[0]]
    assert first is not None
    assert (
        first.total_count,
        first.annotated_count,
        first.abnormal_count,
        first.failed_count,
        first.pending_count,
    ) == (5, 1, 1, 2, 1)
    assert counts[collection_jobs[1]] is None  # conflicting persisted prompt versions
    assert counts[collection_jobs[2]] is None  # one target has no persisted prompt identity
    empty = counts[collection_jobs[3]]
    assert empty is not None
    assert empty.total_count == 0
    assert counts[collection_jobs[4]] is None  # no owner-scoped collection Job
    assert seen_contexts == [(owner_id, set(collection_jobs))]
    assert job_reads == [owner_id]
    assert len(session.queries) == 1
    assert owner_id in session.queries[0].compile().params.values()


def test_collection_analysis_counts_rejects_unbounded_or_duplicate_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AnnotationSession([])
    service = AnalysisService(cast(Session, session))
    owner_id, topic_id, version_id = uuid4(), uuid4(), uuid4()
    with pytest.raises(ValueError, match="at most 100 jobs"):
        service.collection_analysis_counts_in_transaction(
            owner_id=owner_id,
            targets_by_job={uuid4(): (topic_id, 1, ()) for _ in range(101)},
        )

    job_id = uuid4()
    monkeypatch.setattr(
        "analysis.services.load_content_job_contexts",
        lambda *_args, **_kwargs: {
            job_id: SimpleNamespace(configuration_ref=f"topic:{topic_id}", configuration_version=1)
        },
    )
    with pytest.raises(ValueError, match="must be distinct"):
        service.collection_analysis_counts_in_transaction(
            owner_id=owner_id,
            targets_by_job={job_id: (topic_id, 1, (version_id, version_id))},
        )


def test_failed_analysis_job_overrides_persisted_pending_annotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id, topic_id, collection_job_id, version_id = (uuid4() for _ in range(4))
    session = AnnotationSession([(topic_id, 1, version_id, "frozen-v1", "pending")])
    context = SimpleNamespace(configuration_ref=f"topic:{topic_id}", configuration_version=1)
    monkeypatch.setattr(
        "analysis.services.load_content_job_contexts",
        lambda *_args, **_kwargs: {collection_job_id: context},
    )
    expected_owner_id = owner_id

    class JobsDomain:
        def __init__(self, _session: object) -> None:
            pass

        def list_analysis_jobs_in_transaction(
            self, *, owner_id: UUID, topic_ids: set[UUID] | None = None
        ) -> tuple[object, ...]:
            assert owner_id == expected_owner_id
            assert topic_ids == {topic_id}
            return (
                _job(
                    topic_id=topic_id,
                    rule_version=1,
                    prompt_version="frozen-v1",
                    version_ids=(version_id,),
                    status=JobStatus.FAILED,
                ),
            )

    monkeypatch.setattr("analysis.services.CollectionDueWindowService", JobsDomain)
    counts = AnalysisService(cast(Session, session)).collection_analysis_counts_in_transaction(
        owner_id=owner_id,
        targets_by_job={collection_job_id: (topic_id, 1, (version_id,))},
    )[collection_job_id]
    assert counts is not None
    assert counts.total_count == 1
    assert counts.failed_count == 1
    assert counts.pending_count == 0
