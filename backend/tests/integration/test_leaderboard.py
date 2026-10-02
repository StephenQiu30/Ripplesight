from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from leaderboard.configuration import configuration_of
from leaderboard.evidence import FetchResult, ParsedRow
from leaderboard.method.constants import ANCHORS, SCORING_SOURCES
from leaderboard.models import (
    LeaderboardModel,
    LeaderboardRanking,
    LeaderboardRun,
    LeaderboardSnapshot,
    LeaderboardSourceState,
)
from leaderboard.reads import LeaderboardReadService
from leaderboard.refresh import LeaderboardRefreshService
from leaderboard.services import LeaderboardService

pytestmark = pytest.mark.skipif(
    not os.getenv("HOTKEY_TEST_DATABASE_URL"), reason="requires a local isolated test database"
)


def evidence(
    source_key: str, at: datetime, *, models: tuple[str, ...] = ANCHORS[:10]
) -> FetchResult:
    source = next(item for item in SCORING_SOURCES if item.key == source_key)
    rows = tuple(
        ParsedRow(
            slug,
            slug,
            configuration_of([]),
            source.unit,
            source.key,
            float(len(models) - rank),
            source_published_at=at,
        )
        for rank, slug in enumerate(models)
    )
    return FetchResult(
        source_key,
        source_key,
        "https://example.org/" + source_key,
        "fixture",
        "https://example.org/attribution",
        at,
        rows,
        {"benchmarkVersion": "fixture-v1"},
    )


def test_snapshot_selection_hash_verification_and_exclusion_are_persisted() -> None:
    engine = create_engine(os.environ["HOTKEY_TEST_DATABASE_URL"])
    at = datetime(2026, 10, 2, tzinfo=UTC)
    try:
        with Session(engine) as session, session.begin():
            service = LeaderboardService(session)
            first_result = evidence("artificial-analysis", at, models=("gpt-5-4",))
            first = service.store_snapshot(first_result, at=at)
            assert first.changed and first.new_models == 1
            repeated = service.store_snapshot(first_result, at=at + timedelta(hours=1))
            assert not repeated.changed and repeated.snapshot_id == first.snapshot_id
            assert session.scalar(select(func.count()).select_from(LeaderboardSnapshot)) == 1
            stored = session.get(LeaderboardSnapshot, first.snapshot_id)
            assert stored is not None
            assert stored.data["lastSeenAt"] == "2026-10-02T01:00:00.000Z"
            excluded = replace(
                first_result,
                rows=(
                    replace(
                        first_result.rows[0],
                        configuration=replace(
                            configuration_of([]), ineligible="fixture explicit exclusion"
                        ),
                    ),
                ),
            )
            corrected = service.store_snapshot(excluded, at=at + timedelta(hours=2))
            assert corrected.changed and corrected.selected == 0
            inputs = service.build_inputs(at=at + timedelta(hours=2))
            assert not inputs.boards
            assert not inputs.evidence
    finally:
        engine.dispose()


def test_valid_round_read_model_source_refresh_and_failed_round_keep_prior_publication() -> None:
    engine = create_engine(os.environ["HOTKEY_TEST_DATABASE_URL"])
    at = datetime(2026, 10, 2, tzinfo=UTC)
    keys = (
        "artificial-analysis",
        "arena-text",
        "deepswe-v1-1",
        "livebench-reasoning",
        "epoch-simpleqa",
        "vals-finance-agent",
    )
    try:
        with Session(engine) as session, session.begin():
            service = LeaderboardService(session)
            for key in keys:
                service.store_snapshot(evidence(key, at), at=at)
            result = service.run_round(at=at)
            assert result.status == "published" and result.reason is None
            assert session.scalar(select(func.count()).select_from(LeaderboardRanking)) == 50
            reads = LeaderboardReadService(session)
            board = reads.board()
            assert board.run.id == result.run_id
            assert board.board.solver_optimal and board.board.connected_components == 1
            assert [entry.model.slug for entry in board.entries] == list(ANCHORS[:10])
            model = reads.model(ANCHORS[0])
            assert not model.historical and model.metric_count == 6
            assert len(model.comparisons) == 5
            assert sum(len(group.items) for group in model.evidence) == 6
            assert reads.source("epoch-simpleqa").rows[0].source_rank == 1
            assert reads.rules().anchors == list(ANCHORS)
            assert reads.sources().run.id == result.run_id
            unchanged = service.run_round(at=at + timedelta(hours=1))
            assert unchanged.status == "unchanged" and unchanged.run_id == result.run_id
            for key in keys:
                service.store_snapshot(evidence(key, at), at=at + timedelta(hours=2))
            refreshed = service.run_round(at=at + timedelta(hours=2))
            assert refreshed.status == "refreshed" and refreshed.run_id != result.run_id
            assert session.scalar(select(func.count()).select_from(LeaderboardRanking)) == 100
            for key in keys:
                service.store_snapshot(
                    evidence(key, at, models=ANCHORS[:2]), at=at + timedelta(hours=3)
                )
            # Explicit omission is eligible for same-protocol carry-forward; expiry removes it.
            failed = service.run_round(at=at + timedelta(days=8), force=True)
            assert failed.status == "failed"
            assert service.latest_published().id == refreshed.run_id
            assert reads.board().run.id == refreshed.run_id
            assert session.get(LeaderboardRun, failed.run_id).failure_reason
            assert session.scalar(select(func.count()).select_from(LeaderboardModel)) == 10
    finally:
        engine.dispose()


def test_source_failure_shrink_and_force_keep_last_valid_evidence_and_last_ok() -> None:
    engine = create_engine(os.environ["HOTKEY_TEST_DATABASE_URL"])
    at = datetime(2026, 10, 2, tzinfo=UTC)

    class FixtureClient:
        requests = 1

        def __init__(self, output: FetchResult | None) -> None:
            self.output = output

        def fetch(self, name: str) -> tuple[FetchResult, ...]:
            assert name == "artificial-analysis"
            if self.output is None:
                raise RuntimeError("fixture upstream is unavailable")
            return (self.output,)

    try:
        with Session(engine) as session, session.begin():
            from typing import Any, cast

            result = evidence("artificial-analysis", at)
            output: list[FetchResult | None] = [result]
            refresh = LeaderboardRefreshService(
                session, lambda: cast(Any, FixtureClient(output[0]))
            )
            good = refresh.fetch_sources(keys=("artificial-analysis",), at=at)
            assert good[0]["ok"] and good[0]["rows"] == 10
            snapshot = session.scalar(select(LeaderboardSnapshot))
            assert snapshot is not None
            output[0] = None
            failed = refresh.fetch_sources(
                keys=("artificial-analysis",), at=at + timedelta(hours=1)
            )
            assert not failed[0]["ok"] and failed[0]["last_ok_at"] == at
            assert session.scalar(select(func.count()).select_from(LeaderboardSnapshot)) == 1
            output[0] = replace(result, rows=result.rows[:4])
            shrink = refresh.fetch_sources(
                keys=("artificial-analysis",), at=at + timedelta(hours=2)
            )
            assert shrink[0]["error_code"] == "suspicious_row_count_shrink"
            assert session.scalar(select(func.count()).select_from(LeaderboardSnapshot)) == 1
            forced = refresh.fetch_sources(
                keys=("artificial-analysis",), at=at + timedelta(hours=3), force=True
            )
            assert forced[0]["ok"] and forced[0]["rows"] == 4
            assert session.scalar(select(func.count()).select_from(LeaderboardSnapshot)) == 2
            assert session.get(
                LeaderboardSourceState, "artificial-analysis"
            ).last_ok_at == at + timedelta(hours=3)
    finally:
        engine.dispose()
