from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import typer
from pydantic import ValidationError
from sqlalchemy import select

from ai.services import AI_COMPONENT_KEY
from core.config import get_settings
from core.errors import ApplicationError
from db.session import create_db_engine, create_session_factory
from identity.models import IdentityUser
from identity.services import IdentityService
from jobs.coverage import CollectionCoverageQueryService
from jobs.schemas import (
    BudgetMetric,
    BudgetPolicyInput,
    BudgetScopeKind,
    ComponentPolicyInput,
    CostClass,
)
from jobs.services import JobObservationService, ResourceBudgetService
from sources.contracts import SourceCapability

jobs_app = typer.Typer(no_args_is_help=True)


@jobs_app.command("coverage-metrics")
def coverage_metrics(
    owner_id: Annotated[UUID, typer.Option(help="Owner whose visible sources are measured.")],
    start: Annotated[str, typer.Option(help="UTC ISO 8601 due-window start (inclusive).")],
    end: Annotated[str, typer.Option(help="UTC ISO 8601 due-window end (exclusive).")],
    source_key: Annotated[str | None, typer.Option(help="Optional source key.")] = None,
    capability: Annotated[
        SourceCapability | None, typer.Option(help="Optional capability.")
    ] = None,
    topic_id: Annotated[UUID | None, typer.Option(help="Optional topic ID.")] = None,
) -> None:
    """Print the same owner-scoped metric DTO as GET /collection-coverage/metrics."""
    start_at = _parse_utc_datetime(start, option="--start")
    end_at = _parse_utc_datetime(end, option="--end")
    settings = get_settings()
    engine = create_db_engine(settings)
    try:
        with create_session_factory(engine)() as session:
            try:
                result = CollectionCoverageQueryService(
                    session, hotlist_interval_seconds=settings.hotlist_interval_seconds
                ).get_metrics(
                    owner_id=owner_id,
                    start=start_at,
                    end=end_at,
                    source_key=source_key,
                    capability=capability,
                    topic_id=topic_id,
                )
            except ValueError as error:
                raise typer.BadParameter(str(error), param_hint="--start/--end") from error
    finally:
        engine.dispose()
    typer.echo(json.dumps(result.model_dump(mode="json"), allow_nan=False, separators=(",", ":")))


def _parse_utc_datetime(value: str, *, option: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise typer.BadParameter(
            "expected an ISO 8601 timestamp with a timezone", param_hint=option
        ) from error
    if parsed.utcoffset() is None:
        raise typer.BadParameter("timestamp must include a timezone", param_hint=option)
    return parsed.astimezone(UTC)


@jobs_app.command("reliability-snapshot")
def reliability_snapshot(
    window_start: Annotated[
        str,
        typer.Option(help="ISO 8601 observation-window start, including timezone."),
    ],
    window_end: Annotated[
        str,
        typer.Option(help="ISO 8601 observation-window end, including timezone."),
    ],
) -> None:
    """Print a read-only, reproducible webpage.collect reliability snapshot as JSON."""
    start = _parse_utc_datetime(window_start, option="--window-start")
    end = _parse_utc_datetime(window_end, option="--window-end")
    if end <= start:
        raise typer.BadParameter("window end must follow window start", param_hint="--window-end")

    engine = create_db_engine(get_settings())
    try:
        sessions = create_session_factory(engine)
        with sessions() as session:
            owner_id = session.scalar(select(IdentityUser.id))
            if owner_id is None:
                typer.echo("Reliability snapshot failed: identity_uninitialized", err=True)
                raise typer.Exit(code=1)
            snapshot = JobObservationService(session).reliability_snapshot(
                owner_id=owner_id,
                window_start=start,
                window_end=end,
            )
    finally:
        engine.dispose()

    payload = snapshot.model_dump(mode="json")
    payload["owner_id"] = str(owner_id)
    payload["on_time_rate"] = snapshot.on_time_rate
    typer.echo(json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True))


_BASELINE_ANCHOR = datetime(2026, 1, 1, tzinfo=UTC)
_DAY_SECONDS = 86_400


@jobs_app.command("budget-baseline")
def budget_baseline(
    network_daily: Annotated[
        int, typer.Option(min=1, help="Global daily cap on outbound source requests.")
    ] = 5_000,
    analysis_daily: Annotated[
        int, typer.Option(min=1, help="Global daily cap on Codex analysis attempts.")
    ] = 500,
    codex_version: Annotated[
        str, typer.Option(help="Local Codex app-server version recorded on the policy.")
    ] = "0.157.0",
) -> None:
    """Upsert the global budgets and local Codex policy that real execution requires."""
    settings = get_settings()
    engine = create_db_engine(settings)
    session = create_session_factory(engine)()
    try:
        owner_id = IdentityService(session, settings).initialized_owner_id()
        with session.begin():
            budgets = ResourceBudgetService(session)
            for budget_key, metric, limit_units in (
                ("global.network.daily", BudgetMetric.NETWORK_REQUEST, network_daily),
                ("global.analysis.daily", BudgetMetric.ANALYSIS_ATTEMPT, analysis_daily),
            ):
                budgets.save_budget_policy_in_transaction(
                    owner_id=owner_id,
                    command=BudgetPolicyInput(
                        budget_key=budget_key,
                        metric=metric,
                        scope_kind=BudgetScopeKind.GLOBAL,
                        limit_units=limit_units,
                        window_seconds=_DAY_SECONDS,
                        window_anchor_at=_BASELINE_ANCHOR,
                        enabled=True,
                    ),
                )
            budgets.save_component_policy_in_transaction(
                owner_id=owner_id,
                command=ComponentPolicyInput(
                    component_key=AI_COMPONENT_KEY,
                    component_version=codex_version,
                    cost_class=CostClass.LOCAL,
                    enabled_for_core=True,
                    terms_reference="local-codex-app-server",
                    reviewed_at=datetime.now(UTC),
                ),
            )
    except (ApplicationError, ValidationError, ValueError) as error:
        code = error.code if isinstance(error, ApplicationError) else "invalid_budget_baseline"
        typer.echo(f"Budget baseline failed: {code}", err=True)
        raise typer.Exit(code=1) from error
    finally:
        session.close()
        engine.dispose()
    typer.echo(
        f"Budget baseline applied: network/day {network_daily}; "
        f"analysis/day {analysis_daily}; codex {codex_version}"
    )
