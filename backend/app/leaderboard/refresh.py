"""Bounded source refresh, ordered persistence and partial-source failure recovery."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from math import isfinite
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from leaderboard.evidence import FetchResult
from leaderboard.fetch import SOURCE_KEYS, LeaderboardFetchClient
from leaderboard.models import LeaderboardFxRate, LeaderboardSnapshot, LeaderboardSourceState
from leaderboard.schemas import RoundResultView
from leaderboard.services import LeaderboardService


def plausible(
    result: FetchResult, previous_count: int | None, *, force: bool = False
) -> str | None:
    if not result.rows:
        return "no_rows_parsed"
    if not force and previous_count and len(result.rows) < previous_count / 2:
        return "suspicious_row_count_shrink"
    return None


class LeaderboardRefreshService:
    """Run from a worker, with a request-budget-aware client factory.

    At most two independent fetchers wait at once. All ORM writes occur in the
    calling thread in the original registry order, preserving alias resolution.
    Each source has its own savepoint: one failure keeps its latest evidence and
    does not roll back other successful snapshots. The outer caller commits.
    """

    def __init__(
        self,
        session: Session,
        client_factory: Callable[[], LeaderboardFetchClient],
        *,
        named_client_factory: Callable[[str], LeaderboardFetchClient] | None = None,
    ) -> None:
        self.session, self.client_factory = session, client_factory
        self.named_client_factory = named_client_factory

    def _client(self, name: str) -> LeaderboardFetchClient:
        return (
            self.named_client_factory(name) if self.named_client_factory else self.client_factory()
        )

    def _state(
        self,
        key: str,
        *,
        now: datetime,
        request_count: int,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> None:
        previous = self.session.get(LeaderboardSourceState, key)
        state = previous or LeaderboardSourceState(source_key=key)
        state.ok, state.checked_at, state.request_count = error_code is None, now, request_count
        state.last_ok_at = now if error_code is None else previous.last_ok_at if previous else None
        state.changed = result.get("changed") if result else None
        state.row_count = result.get("rows") if result else None
        state.new_models = result.get("new_models") if result else None
        state.error_code = error_code
        if previous is None:
            self.session.add(state)

    def fetch_sources(
        self,
        *,
        keys: tuple[str, ...] | None = None,
        force: bool = False,
        at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = at or datetime.now(UTC)
        collectors = tuple(
            name
            for name, source_keys in SOURCE_KEYS.items()
            if keys is None or any(key in keys for key in source_keys)
        )
        if keys is not None and set(keys) - {
            key for values in SOURCE_KEYS.values() for key in values
        }:
            raise ValueError("Unknown leaderboard source key")
        service = LeaderboardService(self.session)
        for start in range(0, len(collectors), 2):
            batch = collectors[start : start + 2]
            clients = tuple(self._client(name) for name in batch)
            with ThreadPoolExecutor(
                max_workers=2, thread_name_prefix="leaderboard-source"
            ) as executor:
                futures = tuple(
                    executor.submit(client.fetch, name)
                    for client, name in zip(clients, batch, strict=True)
                )
                for name, client, future in zip(batch, clients, futures, strict=True):
                    try:
                        fetched = future.result()
                    except Exception as error:
                        # Any malformed provider shape fails only its own source; never expose
                        # response content or credentials in durable operational state.
                        for key in SOURCE_KEYS[name]:
                            if keys is None or key in keys:
                                self._state(
                                    key,
                                    now=now,
                                    request_count=client.requests,
                                    error_code=type(error).__name__,
                                )
                        continue
                    by_key = {result.source_key: result for result in fetched}
                    for key in SOURCE_KEYS[name]:
                        if keys is not None and key not in keys:
                            continue
                        if key not in by_key:
                            self._state(
                                key,
                                now=now,
                                request_count=client.requests,
                                error_code="missing_source_result",
                            )
                            continue
                        result = by_key[key]
                        previous = self.session.scalar(
                            select(LeaderboardSnapshot)
                            .where(LeaderboardSnapshot.source_key == key)
                            .order_by(LeaderboardSnapshot.fetched_at.desc())
                            .limit(1)
                        )
                        count = previous.data.get("rawRowCount") if previous else None
                        problem = plausible(
                            result, int(count) if count is not None else None, force=force
                        )
                        if problem:
                            self._state(
                                key, now=now, request_count=client.requests, error_code=problem
                            )
                            continue
                        try:
                            with self.session.begin_nested():
                                stored = service.store_snapshot(result, at=now)
                            self._state(
                                key,
                                now=now,
                                request_count=client.requests,
                                result=stored.model_dump(),
                            )
                        except (RuntimeError, ValueError, SQLAlchemyError) as error:
                            self._state(
                                key,
                                now=now,
                                request_count=client.requests,
                                error_code=type(error).__name__,
                            )
        self.session.flush()
        return self.source_states()

    def source_states(self) -> list[dict[str, Any]]:
        return [
            {
                "source_key": state.source_key,
                "ok": state.ok,
                "checked_at": state.checked_at,
                "last_ok_at": state.last_ok_at,
                "changed": state.changed,
                "rows": state.row_count,
                "new_models": state.new_models,
                "request_count": state.request_count,
                "error_code": state.error_code,
            }
            for state in self.session.scalars(
                select(LeaderboardSourceState).order_by(LeaderboardSourceState.source_key)
            )
        ]

    def refresh_fx(self) -> dict[str, Any]:
        client = self._client("fx")
        quote = client.fetch_fx()
        as_of = date.fromisoformat(quote["date"])
        rate = float(quote["rates"]["CNY"])
        if not isfinite(rate) or rate <= 0:
            raise ValueError("Exchange rate must be finite and positive")
        self.session.execute(
            insert(LeaderboardFxRate)
            .values(
                id=uuid4(),
                pair="USD/CNY",
                as_of=as_of,
                rate=rate,
                source_name="欧洲央行",
                source_url="https://api.frankfurter.app/latest?from=USD&to=CNY",
            )
            .on_conflict_do_nothing(
                index_elements=[LeaderboardFxRate.pair, LeaderboardFxRate.as_of]
            )
        )
        self.session.flush()
        return {"as_of": as_of, "rate": rate, "request_count": client.requests}

    def refresh(
        self,
        *,
        at: datetime | None = None,
        force: bool = False,
        keys: tuple[str, ...] | None = None,
        time_limit_seconds: float = 300,
    ) -> tuple[RoundResultView, dict[str, Any]]:
        now = at or datetime.now(UTC)
        states = self.fetch_sources(keys=keys, force=force, at=now)
        try:
            with self.session.begin_nested():
                fx = self.refresh_fx()
        except (RuntimeError, ValueError, KeyError, SQLAlchemyError, httpx.HTTPError) as error:
            fx = {"error_code": type(error).__name__}
        service = LeaderboardService(self.session)
        with self.session.begin_nested():
            prices = service.import_official_prices(at=now)
        round_ = service.run_round(at=now, force=force, time_limit_seconds=time_limit_seconds)
        return round_, {"sources": states, "fx": fx, "prices": prices}
