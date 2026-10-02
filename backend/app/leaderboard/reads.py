"""Public reads of the last valid stored run; no fetches or solver calls."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import ApplicationError, DependencyUnavailableError
from leaderboard.configuration import cloaked_model
from leaderboard.method.constants import (
    ANCHORS,
    BUDGETS,
    CARRY_FORWARD_DAYS,
    CONFIGURATION_POLICY,
    DISPLAY_METHOD,
    METHOD_VERSION,
    RELEASE_WINDOW_MONTHS,
    SCORE_DEFINITION,
    SCORING_SOURCES,
)
from leaderboard.method.run import TIE_POLICY
from leaderboard.models import (
    LeaderboardModel,
    LeaderboardPrice,
    LeaderboardRanking,
    LeaderboardRun,
    LeaderboardScore,
    LeaderboardSnapshot,
)
from leaderboard.registry import (
    BOARD_LIMIT,
    PUBLIC_BOARDS,
    RegistrySource,
    format_score,
    model_access,
    model_brand,
    registry_source,
    score_format,
    source_brand,
    source_groups,
    source_key_of_unit,
)
from leaderboard.schemas import (
    AccessView,
    BoardKey,
    BoardMetaView,
    BoardTabView,
    BoardView,
    BrandView,
    BudgetView,
    CategoryRankView,
    ComparisonRowView,
    ComparisonView,
    EvidenceGroupView,
    EvidenceItemView,
    MissingEvidenceView,
    ModelDetailView,
    ModelRefView,
    PendingModelView,
    PriceView,
    RankingEntryView,
    RulesView,
    RunView,
    SourceDetailView,
    SourceGroupView,
    SourceRowView,
    SourceSummaryView,
    SourcesView,
    StabilityView,
)
from leaderboard.services import LeaderboardService

_BOARD_COPY = {
    "overall": (
        "综合",
        "汇集多种能力的公开评测, 比较模型的综合表现。",
        "综合多家公开评测, 不同模型的参评覆盖不同。",
    ),
    "coding": (
        "编程",
        "从写代码到改仓库, 看模型能不能把软件做出来。",
        "综合多家公开评测, 不同模型的参评覆盖不同。",
    ),
    "reasoning": (
        "推理",
        "数学、逻辑与陌生规则, 比较模型推理表现。",
        "综合多家公开评测, 不同模型的参评覆盖不同。",
    ),
    "knowledge": (
        "知识",
        "事实问答与研究生级科学知识。",
        "当前知识榜采用 Epoch 的两项评测, 来自同一家机构。",
    ),
    "professional": (
        "专业办公",
        "金融分析、法律咨询与银行业务。",
        "当前覆盖金融分析、专业咨询与银行业务, 尚不能代表所有文档、表格和演示文稿任务。",
    ),
}


def _ref(model: LeaderboardModel) -> ModelRefView:
    return ModelRefView(
        slug=model.slug,
        name=model.name,
        provider=None if model.provider == "其他" else model.provider,
        released_at=model.released_at.date() if model.released_at else None,
        brand=BrandView.model_validate(
            asdict(model_brand(model.slug, model.provider_slug, model.provider, model.name))
        ),
    )


def _run_view(run: LeaderboardRun) -> RunView:
    return RunView(
        id=run.id,
        methodology_version=run.methodology_version,
        generated_at=run.generated_at,
        calculated_at=run.summary.get("consensus", {}).get("calculated_at"),
        fingerprint=run.fingerprint,
        fx=run.summary.get("fx_quote"),
    )


def _source_name(key: str) -> str:
    source = registry_source(key)
    return source.source.name if source else key


def _price(price: LeaderboardPrice | None, run: LeaderboardRun) -> PriceView | None:
    if price is None:
        return None
    fx = run.summary.get("fx_quote")
    rate = fx.get("rate") if fx else None

    def cny(value: float | None) -> float | None:
        if value is None:
            return None
        if price.currency == "CNY":
            return value
        return float(value * rate) if price.currency == "USD" and rate else None

    return PriceView(
        currency=price.currency,
        input_price=price.input_price,
        output_price=price.output_price,
        cached_input_price=price.cached_input_price,
        cny_input_price=cny(price.input_price),
        cny_output_price=cny(price.output_price),
        cny_cached_input_price=cny(price.cached_input_price),
        source_url=price.source_url,
        verified_on=price.verified_on,
    )


class LeaderboardReadService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _latest(self, *, required: bool = True) -> LeaderboardRun | None:
        run = LeaderboardService(self.session).latest_published()
        if run is None and required:
            raise DependencyUnavailableError(context={"reason": "no_published_leaderboard_run"})
        return run

    def _rankings(self, run: LeaderboardRun) -> list[tuple[LeaderboardRanking, LeaderboardModel]]:
        return [
            (ranking, model)
            for ranking, model in self.session.execute(
                select(LeaderboardRanking, LeaderboardModel)
                .join(LeaderboardModel, LeaderboardRanking.model_id == LeaderboardModel.id)
                .where(LeaderboardRanking.run_id == run.id)
                .order_by(LeaderboardRanking.board, LeaderboardRanking.rank)
            )
        ]

    def _entry(
        self,
        run: LeaderboardRun,
        ranking: LeaderboardRanking,
        model: LeaderboardModel,
        price: LeaderboardPrice | None = None,
    ) -> RankingEntryView:
        stability = (
            StabilityView.model_validate(ranking.detail["stability"])
            if ranking.detail.get("stability")
            else None
        )
        confidence = (
            "LOW"
            if stability and stability.sensitive
            else "HIGH"
            if ranking.coverage >= 0.7
            else "MEDIUM"
        )
        return RankingEntryView(
            rank=ranking.rank,
            score=ranking.score,
            model=_ref(model),
            source_count=ranking.detail.get("source_count", ranking.metric_count),
            operator_count=ranking.detail.get("operator_count", 0),
            coverage=ranking.coverage,
            confidence=cast(Any, confidence),
            stability=stability,
            price=_price(price, run),
            access=AccessView.model_validate(
                asdict(model_access(model.slug, model.provider_slug, model.provider))
            ),
        )

    def board(
        self, key: BoardKey = "overall", *, domestic: bool = False, open_weights: bool = False
    ) -> BoardView:
        run = self._latest()
        assert run is not None
        consensus = run.summary["consensus"]
        input_ = next((item for item in consensus["input"] if item["board"] == key), None)
        output = next((item for item in consensus["boards"] if item["board"] == key), None)
        if input_ is None or output is None:
            raise ApplicationError("resource_not_found")
        rankings = self._rankings(run)
        prices = {
            price.model_id: price
            for price in self.session.scalars(
                select(LeaderboardPrice).where(LeaderboardPrice.kind == "official")
            )
        }
        entries = [
            self._entry(run, ranking, model, prices.get(model.id))
            for ranking, model in rankings
            if ranking.board == key
        ]

        def subset(domestic_only: bool, weights_only: bool) -> list[RankingEntryView]:
            return [
                entry
                for entry in entries
                if (not domestic_only or entry.access.domestic)
                and (not weights_only or entry.access.weights_url)
            ][:BOARD_LIMIT]

        extension = {
            entry.model.slug: entry
            for entry in [*subset(True, False), *subset(False, True), *subset(True, True)]
            if entry.rank > BOARD_LIMIT
        }
        registry = input_["registry"]
        eligible = {entry.model.slug for entry in entries}
        pending = []
        if key != "overall":
            evidence = consensus.get("evidence", {})
            units = tuple(unit for unit, value in registry.items() if value["weight"] > 0)
            for ranking, model in rankings:
                if ranking.board == "overall" and ranking.rank <= 10 and model.slug not in eligible:
                    present = {
                        source_key_of_unit(unit)
                        for unit in units
                        if f"{unit}:{model.slug}" in evidence
                    }
                    pending.append(PendingModelView(model=_ref(model), sources=len(present)))
        name, description, reading = _BOARD_COPY[key]
        return BoardView(
            run=_run_view(run),
            board=BoardMetaView(
                key=key,
                name=name,
                description=description,
                how_to_read=reading,
                source_count=len(registry),
                operator_count=len(
                    {value["operator"] for value in registry.values() if value["weight"] > 0}
                ),
                model_count=output["model_count"],
                solver_optimal=output["solver"]["optimal"],
                connected_components=output["connected_components"],
                score_definition=output["score_definition"],
                display_method=output["display"]["method"],
                max_optimization_gap=output["display"]["max_optimization_gap"],
                observed_weighted_agreement=output["observed_weighted_agreement"],
            ),
            tabs=[
                BoardTabView(
                    key=cast(BoardKey, board),
                    name=_BOARD_COPY[board][0],
                    href="/leaderboard" if board == "overall" else "/leaderboard/category/" + board,
                )
                for board in PUBLIC_BOARDS
            ],
            entries=subset(domestic, open_weights),
            filter_entries=sorted(extension.values(), key=lambda entry: entry.rank),
            pending=pending,
        )

    def model(self, slug: str) -> ModelDetailView:
        run = self._latest()
        assert run is not None
        model = self.session.scalar(select(LeaderboardModel).where(LeaderboardModel.slug == slug))
        if model is None or cloaked_model(model.slug, model.name):
            raise ApplicationError("resource_not_found")
        historical = False
        current = self.session.scalar(
            select(LeaderboardRanking.id)
            .where(
                LeaderboardRanking.run_id == run.id,
                LeaderboardRanking.model_id == model.id,
                LeaderboardRanking.board.in_(PUBLIC_BOARDS),
            )
            .limit(1)
        )
        if current is None:
            past = self.session.scalar(
                select(LeaderboardRun)
                .join(LeaderboardRanking, LeaderboardRanking.run_id == LeaderboardRun.id)
                .where(
                    LeaderboardRanking.model_id == model.id,
                    LeaderboardRanking.board.in_(PUBLIC_BOARDS),
                    LeaderboardRun.status == "published",
                )
                .order_by(LeaderboardRun.generated_at.desc(), LeaderboardRun.created_at.desc())
                .limit(1)
            )
            if past is None:
                raise ApplicationError("resource_not_found")
            run, historical = past, True
        rankings = self._rankings(run)
        by_board = {ranking.board: ranking for ranking, item in rankings if item.id == model.id}
        consensus = run.summary["consensus"]
        overall_input = next(
            (item for item in consensus["input"] if item["board"] == "overall"), None
        )
        overall_output = next(
            (item for item in consensus["boards"] if item["board"] == "overall"), None
        )
        registry = overall_input["registry"] if overall_input else {}
        scored_units = tuple(unit for unit, value in registry.items() if value["weight"] > 0)
        evidence = consensus.get("evidence", {})
        metas = {
            unit: evidence[f"{unit}:{slug}"]
            for unit in scored_units
            if f"{unit}:{slug}" in evidence
        }
        snapshot_ids = tuple(UUID(item["snapshot_id"]) for item in metas.values())
        details = tuple(
            self.session.scalars(
                select(LeaderboardScore).where(
                    LeaderboardScore.model_id == model.id,
                    LeaderboardScore.snapshot_id.in_(snapshot_ids),
                )
            )
        )
        items: dict[str, EvidenceItemView] = {}
        for unit, meta in metas.items():
            score = next(
                (
                    row
                    for row in details
                    if str(row.snapshot_id) == meta["snapshot_id"]
                    and row.configuration_key == meta["configuration"]
                    and row.metric_key == unit
                ),
                None,
            )
            if score is None:
                continue
            key = source_key_of_unit(unit)
            source = registry_source(key)
            items[key] = EvidenceItemView(
                unit=unit,
                source_key=key,
                source_name=source.source.name if source else key,
                official_url=source.source.official_url if source else None,
                protocol=meta["protocol"],
                snapshot_id=score.snapshot_id,
                raw_score=score.raw_score,
                display=format_score(score.raw_score, score_format(key, score.raw_score)),
                source_rank=score.source_rank,
                source_model_name=score.source_model_name,
                configuration_key=score.configuration_key,
                configuration_label=score.configuration_label,
                selection_reason=score.selection_reason,
                upstream_at=meta.get("published_at"),
                verified_at=meta.get("verified_at"),
                measured_at=meta.get("evaluated_at"),
                carried_forward=meta.get("carried_forward", False),
                components=score.data,
            )
        missing = tuple(
            dict.fromkeys(
                source_key_of_unit(unit)
                for unit in scored_units
                if source_key_of_unit(unit) not in items
            )
        )
        excluded_rows = tuple(
            self.session.scalars(
                select(LeaderboardScore)
                .where(
                    LeaderboardScore.model_id == model.id,
                    LeaderboardScore.snapshot_id.in_(
                        tuple(UUID(id_) for id_ in run.source_snapshot_ids)
                    ),
                    LeaderboardScore.selected_for_product.is_(False),
                )
                .order_by(LeaderboardScore.configuration_priority.desc())
            )
        )
        reasons: dict[str, str] = {}
        for row in excluded_rows:
            reasons.setdefault(source_key_of_unit(row.metric_key), row.selection_reason)

        def category(key: str) -> CategoryRankView:
            rank = by_board.get(key)
            return CategoryRankView(
                key=cast(BoardKey, key),
                name=_BOARD_COPY[key][0],
                rank=rank.rank if rank else None,
                score=rank.score if rank else None,
                source_count=rank.metric_count if rank else 0,
                on_board=bool(rank and rank.rank <= BOARD_LIMIT),
            )

        groups = [
            EvidenceGroupView(
                key=group.key,
                name=group.name,
                items=[items[source.key] for source in group.sources if source.key in items],
            )
            for group in source_groups()
        ]
        price = self.session.scalar(
            select(LeaderboardPrice).where(
                LeaderboardPrice.model_id == model.id, LeaderboardPrice.kind == "official"
            )
        )
        overall = by_board.get("overall")
        comparisons = (
            self._comparisons(model, rankings, overall_input, overall_output, overall)
            if overall and overall_input and overall_output
            else []
        )
        return ModelDetailView(
            run=_run_view(run),
            historical=historical,
            model=_ref(model),
            context_window_tokens=model.context_window_tokens,
            weights_url=model_access(model.slug, model.provider_slug, model.provider).weights_url,
            price=_price(price, run),
            overall=category("overall"),
            overall_stability=StabilityView.model_validate(overall.detail["stability"])
            if overall and overall.detail.get("stability")
            else None,
            categories=[category(key) for key in PUBLIC_BOARDS if key != "overall"],
            metric_count=len(items),
            evidence=[group for group in groups if group.items],
            excluded=[
                MissingEvidenceView(
                    key=key,
                    name=_source_name(key),
                    reason=reasons[key],
                )
                for key in missing
                if key in reasons
            ],
            unmeasured=[
                MissingEvidenceView(key=key, name=_source_name(key))
                for key in missing
                if key not in reasons
            ],
            comparisons=comparisons,
        )

    def _comparisons(
        self,
        model: LeaderboardModel,
        rankings: list[tuple[LeaderboardRanking, LeaderboardModel]],
        input_: dict[str, Any],
        output: dict[str, Any],
        own: LeaderboardRanking,
    ) -> list[ComparisonView]:
        ranked = {
            item.slug: (ranking, item) for ranking, item in rankings if ranking.board == "overall"
        }
        raw = [
            item
            for item in output.get("comparisons", {}).get(model.slug, [])
            if item["slug"] in ranked
        ]
        raw.sort(
            key=lambda item: (
                abs(ranked[item["slug"]][0].rank - own.rank),
                ranked[item["slug"]][0].rank,
            )
        )
        signals = {
            signal["key"]: {row["model_slug"]: row for row in signal["rows"]}
            for signal in input_["signals"]
        }
        comparisons = []
        for item in raw[:5]:
            other_rank, other_model = ranked[item["slug"]]
            rows = []
            for unit, registry in input_["registry"].items():
                signal = signals.get(unit, {})
                if (
                    registry["weight"] <= 0
                    or model.slug not in signal
                    or other_model.slug not in signal
                ):
                    continue
                key = source_key_of_unit(unit)
                source = registry_source(key)
                format_ = score_format(key, signal[model.slug]["score"])
                rows.append(
                    ComparisonRowView(
                        source_key=key,
                        source_name=source.source.name if source else key,
                        official_url=source.source.official_url if source else None,
                        mine=format_score(signal[model.slug]["score"], format_),
                        theirs=format_score(signal[other_model.slug]["score"], format_),
                        weight=registry["weight"],
                    )
                )
            comparisons.append(
                ComparisonView(
                    model=_ref(other_model),
                    rank=other_rank.rank,
                    net=item["net"],
                    shared_weight=item["shared"],
                    shared_count=len(rows),
                    has_page=other_rank.rank <= BOARD_LIMIT,
                    rows=rows,
                )
            )
        return comparisons

    def _source_summary(
        self, source: RegistrySource, run: LeaderboardRun | None
    ) -> SourceSummaryView:
        use = next(
            (
                item
                for item in (run.summary.get("sources", []) if run else [])
                if item["key"] == source.key
            ),
            None,
        )
        fixed = next((item for item in SCORING_SOURCES if item.key == source.key), None)
        return SourceSummaryView(
            key=source.key,
            status=source.status,
            name=source.name,
            operator=source.operator,
            description=source.description,
            brand=BrandView.model_validate(asdict(source_brand(source))),
            weight=float(use["weight"]) if use else fixed.weight if fixed else 0.0,
            family_key=use["family_key"] if use else fixed.family if fixed else None,
            category_key=use["category_key"] if use else fixed.category if fixed else None,
            collected=bool(use and use["used_in_overall"]),
        )

    def sources(self) -> SourcesView:
        run = self._latest(required=False)
        return SourcesView(
            run=_run_view(run) if run else None,
            groups=[
                SourceGroupView(
                    key=group.key,
                    name=group.name,
                    blurb=group.blurb,
                    sources=[self._source_summary(source, run) for source in group.sources],
                )
                for group in source_groups()
            ],
        )

    def source(self, key: str) -> SourceDetailView:
        lookup = registry_source(key)
        if lookup is None:
            raise ApplicationError("resource_not_found")
        run = self._latest(required=False)
        source = lookup.source
        selected_ids = tuple(UUID(id_) for id_ in run.source_snapshot_ids) if run else ()
        snapshot = self.session.scalar(
            select(LeaderboardSnapshot)
            .where(LeaderboardSnapshot.source_key == key)
            .order_by(
                LeaderboardSnapshot.id.in_(selected_ids).desc(),
                LeaderboardSnapshot.fetched_at.desc(),
            )
            .limit(1)
        )
        show = snapshot is not None and source.status in {
            "ranked",
            "cross_reference",
            "reference_only",
        }
        rows: list[SourceRowView] = []
        if snapshot is not None and show:
            selected = [
                (score, model)
                for score, model in self.session.execute(
                    select(LeaderboardScore, LeaderboardModel)
                    .join(LeaderboardModel, LeaderboardScore.model_id == LeaderboardModel.id)
                    .where(LeaderboardScore.snapshot_id == snapshot.id)
                )
            ]
            if not source.all_rows:
                best: dict[tuple[UUID, str], tuple[LeaderboardScore, LeaderboardModel]] = {}
                for score, model in sorted(
                    selected,
                    key=lambda item: (
                        -int(item[0].selected_for_product),
                        -item[0].configuration_priority,
                    ),
                ):
                    best.setdefault((score.model_id, score.metric_key), (score, model))
                selected = list(best.values())
            selected.sort(
                key=lambda item: (
                    item[0].source_rank if item[0].source_rank is not None else 10**9,
                    -item[0].raw_score,
                )
            )
            for score, model in selected:
                if cloaked_model(score.source_model_name, model.slug, model.name):
                    continue
                has_page = (
                    self.session.scalar(
                        select(LeaderboardRanking.id)
                        .where(LeaderboardRanking.model_id == model.id)
                        .limit(1)
                    )
                    is not None
                )
                rows.append(
                    SourceRowView(
                        source_rank=score.source_rank,
                        source_model_name=score.source_model_name,
                        model_slug=model.slug if has_page else None,
                        provider=None if model.provider == "其他" else model.provider,
                        display=format_score(score.raw_score, score_format(key, score.raw_score)),
                        configuration_label=score.configuration_label,
                        excluded=None
                        if source.all_rows or score.selected_for_product
                        else score.selection_reason,
                    )
                )
                if len(rows) == BOARD_LIMIT:
                    break
        synced = (
            snapshot.data.get("lastSeenAt") or snapshot.fetched_at if snapshot and show else None
        )
        return SourceDetailView(
            run=_run_view(run) if run else None,
            source=self._source_summary(source, run),
            full_name=source.full_name or source.name,
            area=source.area,
            official_url=source.official_url,
            what=source.what,
            usage=source.usage,
            limits=source.limits,
            license=source.license,
            attribution=source.attribution,
            upstream_at=snapshot.published_at if snapshot and show else None,
            synced_at=synced,
            collected=show,
            system_rows=source.all_rows,
            rows=rows,
            rows_note=(
                "模型搭配不同 Agent 的系统成绩, 运行条件不同, 仅供参考; 保留原榜名次, 最多 30 条。"
                if source.all_rows
                else (
                    "每个公开模型采用固定优先级代表配置; 排除配置保留原因; "
                    "匿名型号不展示, 保留原榜名次, 最多 30 个。"
                )
            )
            if show
            else None,
        )

    def rules(self) -> RulesView:
        run = self._latest(required=False)
        budgets = run.summary.get("budgets", BUDGETS) if run else BUDGETS
        return RulesView(
            run=_run_view(run) if run else None,
            methodology_version=METHOD_VERSION,
            score_definition=SCORE_DEFINITION,
            display_method=DISPLAY_METHOD,
            tie_policy=TIE_POLICY,
            budgets=[
                BudgetView(
                    key=key,
                    name=name,
                    weight=weight,
                    sources=[source.key for source in SCORING_SOURCES if source.budget == key],
                )
                for key, name, weight in budgets
            ],
            anchors=list(ANCHORS),
            configuration_policy=CONFIGURATION_POLICY,
            carry_forward_days=CARRY_FORWARD_DAYS,
            release_window_months=RELEASE_WINDOW_MONTHS,
        )
