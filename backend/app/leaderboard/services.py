"""Transactional evidence import and worker-only leaderboard round orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import DateTime, or_, select, text
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from leaderboard.configuration import model_slug
from leaderboard.evidence import (
    FetchResult,
    ResolvedRow,
    prepare_rows,
    select_representatives,
    stored_configuration_key,
)
from leaderboard.method.constants import (
    BUDGETS,
    CARRY_FORWARD_DAYS,
    METHOD_VERSION,
    SCORING_SOURCES,
)
from leaderboard.method.inputs import build_run_inputs
from leaderboard.method.run import (
    TIE_POLICY,
    canonical_json,
    compute_boards,
    evidence_fingerprint,
    input_fingerprint,
    publication_failure,
    published_outputs,
)
from leaderboard.method.types import RunInputs, ScoreRow, Snapshot
from leaderboard.models import (
    LeaderboardAlias,
    LeaderboardFxRate,
    LeaderboardModel,
    LeaderboardPrice,
    LeaderboardRanking,
    LeaderboardRun,
    LeaderboardScore,
    LeaderboardSnapshot,
)
from leaderboard.schemas import RoundResultView, SnapshotResultView


def json_data(value: Any) -> Any:
    """JSON-safe immutable input snapshot, including UTC provenance timestamps."""
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if isinstance(value, (UUID, date)):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_data(item) for item in value]
    return value


def snapshot_content_hash(result: FetchResult, rows: tuple[ResolvedRow, ...]) -> str:
    canon = sorted(
        canonical_json(
            json_data(
                [
                    item.row.source_model_name,
                    stored_configuration_key(item.row),
                    item.row.metric_key,
                    item.row.metric_name,
                    item.row.raw_score,
                    item.row.lower_bound,
                    item.row.upper_bound,
                    item.model_id,
                    item.selected,
                    item.selection_reason,
                    item.row.configuration.label,
                    item.row.configuration.kind,
                    item.row.configuration.priority,
                    item.row.source_rank,
                    item.row.sample_size,
                    item.row.organization,
                    item.row.source_published_at,
                    item.row.metadata,
                ]
            )
        )
        for item in rows
    )
    payload = json_data(
        {
            "source_name": result.source_name,
            "source_url": result.source_url,
            "license": result.license,
            "attribution_url": result.attribution_url,
            "published_at": result.published_at,
            "metadata": result.metadata,
            "rows": canon,
        }
    )
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class LeaderboardService:
    """Caller owns begin/commit/rollback; importing evidence never fetches a provider."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def _lock(self, name: str) -> None:
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:name, 0))"), {"name": name}
        )

    def latest_published(self) -> LeaderboardRun | None:
        return self.session.scalar(
            select(LeaderboardRun)
            .where(LeaderboardRun.status == "published")
            .order_by(LeaderboardRun.generated_at.desc(), LeaderboardRun.created_at.desc())
            .limit(1)
        )

    def store_snapshot(
        self, result: FetchResult, *, at: datetime | None = None
    ) -> SnapshotResultView:
        now = at or datetime.now(UTC)
        if now.tzinfo is None:
            raise ValueError("Snapshot verification time must be timezone aware")
        self._lock("leaderboard-source:" + result.source_key)
        rows = prepare_rows(result.rows)
        aliases = {
            alias.alias: alias.model_id
            for alias in self.session.scalars(
                select(LeaderboardAlias).where(LeaderboardAlias.source_key == result.source_key)
            )
        }
        existing = tuple(self.session.scalars(select(LeaderboardModel)))
        by_slug = {model.slug: model.id for model in existing}
        slugs = {str(model.id): model.slug for model in existing}
        ids: list[str] = []
        new_models = 0
        for row in rows:
            names = (row.source_model_name, *row.alt_names)
            model_id = next((aliases[name] for name in names if name in aliases), None)
            slug = model_slug(row.base_name)
            if not slug:
                raise ValueError("A source base name must resolve to a nonempty model slug")
            if model_id is None:
                model_id = by_slug.get(slug)
                if model_id is None:
                    candidate = uuid4()
                    inserted = self.session.scalar(
                        insert(LeaderboardModel)
                        .values(
                            id=candidate,
                            slug=slug,
                            name=row.base_name,
                            provider=row.organization or "其他",
                            provider_slug="other",
                            released_at=row.released_at,
                            release_date_source=result.source_key if row.released_at else None,
                            metadata_source=result.source_key,
                            context_window_tokens=None,
                            created_at=now,
                            updated_at=now,
                        )
                        .on_conflict_do_nothing(index_elements=[LeaderboardModel.slug])
                        .returning(LeaderboardModel.id)
                    )
                    if inserted is None:
                        model_id = self.session.scalar(
                            select(LeaderboardModel.id).where(LeaderboardModel.slug == slug)
                        )
                        if model_id is None:
                            raise RuntimeError("Concurrent model insertion did not resolve")
                    else:
                        model_id = inserted
                        new_models += 1
                    by_slug[slug], slugs[str(model_id)] = model_id, slug
            for name in names:
                self.session.execute(
                    insert(LeaderboardAlias)
                    .values(
                        id=uuid4(),
                        source_key=result.source_key,
                        alias=name,
                        normalized_alias=slug,
                        model_id=model_id,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[LeaderboardAlias.source_key, LeaderboardAlias.alias]
                    )
                )
                aliases.setdefault(name, model_id)
            ids.append(str(model_id))
        resolved = select_representatives(rows, ids, slugs)
        content_hash = snapshot_content_hash(result, resolved)
        latest = self.session.scalar(
            select(LeaderboardSnapshot)
            .where(LeaderboardSnapshot.source_key == result.source_key)
            .order_by(LeaderboardSnapshot.fetched_at.desc())
            .limit(1)
        )
        selected = sum(item.selected for item in resolved)
        if latest and latest.content_hash == content_hash:
            latest.data = {**latest.data, "lastSeenAt": json_data(now)}
            self.session.flush()
            return SnapshotResultView(
                snapshot_id=latest.id,
                changed=False,
                rows=len(resolved),
                selected=selected,
                new_models=new_models,
            )
        metadata = {
            **result.metadata,
            "parserVersion": "hotkey-python-1",
            "firstSeenAt": json_data(now),
            "lastSeenAt": json_data(now),
            "rawRowCount": len(result.rows),
            "configurationRecordCount": len(resolved),
            "newModelCount": new_models,
            "metricModelCounts": {
                metric: sum(item.selected and item.row.metric_key == metric for item in resolved)
                for metric in dict.fromkeys(item.row.metric_key for item in resolved)
            },
        }
        snapshot_id = uuid4()
        self.session.add(
            LeaderboardSnapshot(
                id=snapshot_id,
                source_key=result.source_key,
                source_name=result.source_name,
                source_url=result.source_url,
                license=result.license,
                attribution_url=result.attribution_url,
                content_hash=content_hash,
                published_at=result.published_at,
                fetched_at=now,
                record_count=selected,
                data=json_data(metadata),
            )
        )
        self.session.flush()
        for item in resolved:
            row = item.row
            self.session.add(
                LeaderboardScore(
                    id=uuid4(),
                    snapshot_id=snapshot_id,
                    model_id=UUID(item.model_id),
                    configuration_key=stored_configuration_key(row),
                    configuration_label=row.configuration.label,
                    configuration_kind=row.configuration.kind,
                    configuration_priority=row.configuration.priority,
                    selected_for_product=item.selected,
                    selection_reason=item.selection_reason,
                    metric_key=row.metric_key,
                    metric_name=row.metric_name,
                    raw_score=row.raw_score,
                    lower_bound=row.lower_bound,
                    upper_bound=row.upper_bound,
                    source_rank=row.source_rank,
                    sample_size=row.sample_size,
                    source_model_name=row.source_model_name,
                    source_organization=row.organization,
                    source_published_at=row.source_published_at,
                    data=json_data(
                        {
                            **row.metadata,
                            "configurationKind": row.configuration.kind,
                            "configurationLabel": row.configuration.label,
                        }
                    ),
                )
            )
        self.session.flush()
        return SnapshotResultView(
            snapshot_id=snapshot_id,
            changed=True,
            rows=len(resolved),
            selected=selected,
            new_models=new_models,
        )

    def build_inputs(
        self, *, at: datetime, snapshot_ids: tuple[UUID, ...] | None = None
    ) -> RunInputs:
        if snapshot_ids is not None:
            chosen = tuple(
                self.session.scalars(
                    select(LeaderboardSnapshot).where(LeaderboardSnapshot.id.in_(snapshot_ids))
                )
            )
        else:
            keys = tuple(dict.fromkeys(source.key for source in SCORING_SOURCES))
            latest = tuple(
                self.session.scalars(
                    select(LeaderboardSnapshot)
                    .where(
                        LeaderboardSnapshot.source_key.in_(keys),
                        LeaderboardSnapshot.fetched_at <= at,
                    )
                    .distinct(LeaderboardSnapshot.source_key)
                    .order_by(LeaderboardSnapshot.source_key, LeaderboardSnapshot.fetched_at.desc())
                )
            )
            cutoff = at - timedelta(days=CARRY_FORWARD_DAYS)
            recent = tuple(
                self.session.scalars(
                    select(LeaderboardSnapshot).where(
                        LeaderboardSnapshot.source_key.in_(keys),
                        LeaderboardSnapshot.fetched_at <= at,
                        or_(
                            LeaderboardSnapshot.fetched_at >= cutoff,
                            sql_cast(
                                LeaderboardSnapshot.data["lastSeenAt"].astext,
                                DateTime(timezone=True),
                            )
                            >= cutoff,
                        ),
                    )
                )
            )
            chosen = tuple({snapshot.id: snapshot for snapshot in (*latest, *recent)}.values())
        ids = tuple(snapshot.id for snapshot in chosen)
        records = self.session.execute(
            select(LeaderboardScore, LeaderboardModel)
            .join(LeaderboardModel, LeaderboardScore.model_id == LeaderboardModel.id)
            .where(LeaderboardScore.snapshot_id.in_(ids))
        ).all()
        snapshots = tuple(
            Snapshot(str(item.id), item.source_key, item.fetched_at, item.published_at, item.data)
            for item in chosen
        )
        scores = tuple(
            ScoreRow(
                str(score.snapshot_id),
                score.metric_key,
                model.slug,
                model.name,
                model.released_at,
                score.raw_score,
                score.lower_bound,
                score.upper_bound,
                score.configuration_key,
                score.selected_for_product,
                score.data,
            )
            for score, model in records
        )
        return build_run_inputs(
            snapshots,
            scores,
            at=at,
            snapshot_ids=tuple(str(id_) for id_ in snapshot_ids)
            if snapshot_ids is not None
            else None,
        )

    def _fx_quote(self) -> dict[str, Any] | None:
        fx = self.session.scalar(
            select(LeaderboardFxRate)
            .where(LeaderboardFxRate.pair == "USD/CNY")
            .order_by(LeaderboardFxRate.as_of.desc())
            .limit(1)
        )
        return (
            {
                "as_of": str(fx.as_of),
                "rate": fx.rate,
                "source_name": fx.source_name,
                "source_url": fx.source_url,
            }
            if fx
            else None
        )

    def run_round(
        self,
        *,
        at: datetime | None = None,
        force: bool = False,
        snapshot_ids: tuple[UUID, ...] | None = None,
        time_limit_seconds: float = 300,
    ) -> RoundResultView:
        now = at or datetime.now(UTC)
        self._lock("leaderboard-round")
        inputs = self.build_inputs(at=now, snapshot_ids=snapshot_ids)
        fingerprint = input_fingerprint(inputs.boards)
        latest = self.latest_published()
        fx = self._fx_quote()
        evidence_summary = {
            "fx_quote": fx,
            "sources": json_data([asdict(item) for item in inputs.sources]),
            "categories": json_data([asdict(item) for item in inputs.categories]),
            "consensus": {
                "evidence": json_data({key: asdict(item) for key, item in inputs.evidence.items()})
            },
        }
        if not force and latest and latest.fingerprint == fingerprint:
            refreshed = {
                **latest.summary,
                **{key: value for key, value in evidence_summary.items() if key != "consensus"},
                "consensus": {**latest.summary["consensus"], **evidence_summary["consensus"]},
            }
            if evidence_fingerprint(latest.summary) == evidence_fingerprint(refreshed):
                return RoundResultView(
                    status="unchanged", run_id=latest.id, fingerprint=fingerprint, boards=[]
                )
            run_id = uuid4()
            self.session.add(
                LeaderboardRun(
                    id=run_id,
                    methodology_version=latest.methodology_version,
                    generated_at=now,
                    source_snapshot_ids=list(inputs.snapshot_ids),
                    summary=refreshed,
                    status="published",
                    origin="refreshed",
                    fingerprint=fingerprint,
                    failure_reason=None,
                    created_at=datetime.now(UTC),
                )
            )
            self.session.flush()
            for ranking in self.session.scalars(
                select(LeaderboardRanking).where(LeaderboardRanking.run_id == latest.id)
            ):
                self.session.add(
                    LeaderboardRanking(
                        id=uuid4(),
                        run_id=run_id,
                        board=ranking.board,
                        model_id=ranking.model_id,
                        rank=ranking.rank,
                        score=ranking.score,
                        coverage=ranking.coverage,
                        metric_count=ranking.metric_count,
                        summary=ranking.summary,
                        detail=ranking.detail,
                    )
                )
            self.session.flush()
            return RoundResultView(
                status="refreshed", run_id=run_id, fingerprint=fingerprint, boards=[]
            )
        reason: str | None
        try:
            computed = compute_boards(inputs.boards, time_limit_seconds=time_limit_seconds)
            outputs = published_outputs(inputs.boards, computed.outputs)
            reason = publication_failure(inputs.boards, outputs)
            timings = [asdict(timing) for timing in computed.timings]
            calculated_at = computed.calculated_at
        except (RuntimeError, ValueError) as error:
            outputs, timings, calculated_at = (), [], datetime.now(UTC)
            reason = f"computation failed: {type(error).__name__}"
        summary = {
            **evidence_summary,
            "budgets": json_data(BUDGETS),
            "timings": timings,
            "consensus": {
                **evidence_summary["consensus"],
                "input": json_data([asdict(board) for board in inputs.boards]),
                "boards": json_data([asdict(board) for board in outputs]),
                "version": METHOD_VERSION,
                "tie_policy": TIE_POLICY,
                "fingerprint": fingerprint,
                "calculated_at": json_data(calculated_at),
            },
        }
        run_id = uuid4()
        run_status = "failed" if reason else "published"
        self.session.add(
            LeaderboardRun(
                id=run_id,
                methodology_version=METHOD_VERSION,
                generated_at=now,
                source_snapshot_ids=list(inputs.snapshot_ids),
                summary=summary,
                status=run_status,
                origin="computed",
                fingerprint=fingerprint,
                failure_reason=reason,
                created_at=datetime.now(UTC),
            )
        )
        self.session.flush()
        if run_status == "published":
            all_slugs = tuple(entry.slug for output in outputs for entry in output.entries)
            models = {
                model.slug: model.id
                for model in self.session.scalars(
                    select(LeaderboardModel).where(LeaderboardModel.slug.in_(all_slugs))
                )
            }
            if set(all_slugs) - set(models):
                raise RuntimeError(
                    "A computed ranking references a model missing from the evidence ledger"
                )
            for output in outputs:
                for entry in output.entries:
                    self.session.add(
                        LeaderboardRanking(
                            id=uuid4(),
                            run_id=run_id,
                            board=output.board,
                            model_id=models[entry.slug],
                            rank=entry.rank,
                            score=entry.score,
                            coverage=entry.coverage,
                            metric_count=entry.source_count,
                            summary=f"{entry.source_count} 项评测 · {entry.operator_count} 家机构",
                            detail={
                                "stability": asdict(entry.stability),
                                "source_count": entry.source_count,
                                "operator_count": entry.operator_count,
                            },
                        )
                    )
        self.session.flush()
        return RoundResultView(
            status=cast(Any, run_status),
            run_id=run_id,
            fingerprint=fingerprint,
            boards=timings,
            reason=reason,
        )

    def import_directory(
        self, *, file: Path | None = None, at: datetime | None = None
    ) -> dict[str, int]:
        now = at or datetime.now(UTC)
        path = file or Path(__file__).with_name("model-directory.json")
        directory = json.loads(path.read_text(encoding="utf-8"))
        models = aliases = 0
        for slug, name, provider, provider_slug, released_on in directory["models"]:
            inserted = self.session.scalar(
                insert(LeaderboardModel)
                .values(
                    id=uuid4(),
                    slug=slug,
                    name=name,
                    provider=provider,
                    provider_slug=provider_slug,
                    released_at=datetime.fromisoformat(released_on).replace(tzinfo=UTC)
                    if released_on
                    else None,
                    release_date_source="directory" if released_on else None,
                    metadata_source="directory",
                    context_window_tokens=None,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=[LeaderboardModel.slug])
                .returning(LeaderboardModel.id)
            )
            models += inserted is not None
        ids = {model.slug: model.id for model in self.session.scalars(select(LeaderboardModel))}
        for source_key, names in directory["aliases"].items():
            for alias, slug in names.items():
                if slug not in ids:
                    continue
                inserted = self.session.scalar(
                    insert(LeaderboardAlias)
                    .values(
                        id=uuid4(),
                        source_key=source_key,
                        alias=alias,
                        normalized_alias=slug,
                        model_id=ids[slug],
                    )
                    .on_conflict_do_nothing(
                        index_elements=[LeaderboardAlias.source_key, LeaderboardAlias.alias]
                    )
                    .returning(LeaderboardAlias.id)
                )
                aliases += inserted is not None
        self.session.flush()
        return {"models": models, "aliases": aliases}

    def import_official_prices(
        self, *, file: Path | None = None, overwrite: bool = False, at: datetime | None = None
    ) -> dict[str, Any]:
        now = at or datetime.now(UTC)
        seed = json.loads(
            (file or Path(__file__).with_name("official-prices.json")).read_text(encoding="utf-8")
        )
        ids = {model.slug: model.id for model in self.session.scalars(select(LeaderboardModel))}
        written, unknown = 0, []
        for slug, (currency, input_, output, cached, url) in seed["prices"].items():
            if slug not in ids:
                unknown.append(slug)
                continue
            values = {
                "id": uuid4(),
                "model_id": ids[slug],
                "kind": "official",
                "currency": currency,
                "input_price": input_,
                "output_price": output,
                "cached_input_price": cached,
                "source_url": url,
                "verified_on": date.fromisoformat(seed["verifiedOn"]),
                "updated_at": now,
            }
            statement = insert(LeaderboardPrice).values(**values)
            if overwrite:
                statement = statement.on_conflict_do_update(
                    index_elements=[LeaderboardPrice.model_id, LeaderboardPrice.kind],
                    set_={
                        key: value
                        for key, value in values.items()
                        if key not in ("id", "model_id", "kind")
                    },
                )
            else:
                statement = statement.on_conflict_do_nothing(
                    index_elements=[LeaderboardPrice.model_id, LeaderboardPrice.kind]
                )
            written += self.session.scalar(statement.returning(LeaderboardPrice.id)) is not None
        self.session.flush()
        return {"written": written, "unknown": unknown}
