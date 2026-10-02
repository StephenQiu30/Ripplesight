"""Ten AIHOT benchmark collectors and pure parsers, adapted under MIT.

The transport is disabled unless the caller explicitly grants both access and
per-request budget. Importing or parsing fixture data never requests a provider.
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import isfinite
from typing import Any, Literal, cast
from urllib.parse import quote, urljoin

import httpx

from leaderboard.configuration import (
    REASONS,
    Configuration,
    configuration_of,
    peel_effort_suffix,
    peel_tier_suffix,
    scaffolded,
    split_name,
)
from leaderboard.evidence import FetchResult, ParsedRow
from sources.adapters.web_targets import normalize_web_url

SOURCE_KEYS = {
    "artificial-analysis": ("artificial-analysis",),
    "arena": ("arena-text", "arena-creative-writing", "arena-webdev", "arena-vision"),
    "livebench": (
        "livebench-general",
        "livebench-writing",
        "livebench-coding",
        "livebench-reasoning",
    ),
    "eqbench": ("eq-creative", "eq-longform"),
    "epoch": (
        "epoch-frontiermath",
        "epoch-frontiermath-tier4",
        "epoch-chess",
        "epoch-mystery",
        "epoch-simpleqa",
        "epoch-gpqa",
        "epoch-mirrorcode",
        "epoch-ebr",
    ),
    "deepswe": ("deepswe-v1-1",),
    "taptap": ("taptap-maker",),
    "mercor": ("mercor-apex-agents",),
    "vals": ("vals-finance-agent",),
    "terminal-bench": ("terminal-bench-4",),
}
_EPOCH_BOARDS = (
    (
        "epoch-frontiermath",
        "FrontierMath v2 · Tiers 1-3",
        "frontiermath_tiers_1_3_v2.csv",
        "frontiermath-tiers-1-3-v2",
    ),
    (
        "epoch-frontiermath-tier4",
        "FrontierMath v2 · Tier 4",
        "frontiermath_tier_4_v2.csv",
        "frontiermath-tier-4-v2",
    ),
    ("epoch-chess", "Chess Puzzles", "chess_puzzles.csv", "chess-puzzles"),
    ("epoch-mystery", "Mystery Game Puzzles", "mystery_game_puzzles.csv", "mystery-game-puzzles"),
    ("epoch-simpleqa", "SimpleQA Verified", "simpleqa_verified.csv", "simple-qa-verified"),
    ("epoch-gpqa", "GPQA Diamond", "gpqa_diamond.csv", "gpqa-diamond"),
    ("epoch-mirrorcode", "MirrorCode", "mirrorcode.csv", "mirrorcode"),
    ("epoch-ebr", "EBR-bench", "ebr_bench.csv", "ebr-bench"),
)
_ARENA_BOARDS = (
    ("arena-text", "Arena Text Style-Controlled", "text_style_control", "overall"),
    ("arena-creative-writing", "Arena Creative Writing", "text_style_control", "creative_writing"),
    ("arena-webdev", "Arena WebDev", "webdev", "overall"),
    ("arena-vision", "Arena Vision Style-Controlled", "vision_style_control", "overall"),
)
_LIVEBENCH_BOARDS = (
    ("livebench-general", "LiveBench Global Average", None),
    ("livebench-writing", "LiveBench · 语言与指令", ("Language", "IF")),
    ("livebench-coding", "LiveBench · 编程综合", ("Coding", "Agentic Coding")),
    ("livebench-reasoning", "LiveBench · 推理与数学", ("Reasoning", "Mathematics")),
)
_EQ_BOARDS = (
    (
        "eq-creative",
        "Creative Writing v3",
        "creative_writing.js",
        "elo_score",
        "creative-writing-v3",
        "creative_writing.html",
    ),
    (
        "eq-longform",
        "Longform Writing",
        "creative_writing_longform.js",
        "overall_score_100",
        "longform-v1.11",
        "creative_writing_longform.html",
    ),
)
_HOSTS = frozenset(
    {
        "artificialanalysis.ai",
        "huggingface.co",
        "cdn-lfs.huggingface.co",
        "cdn-lfs-us-1.hf.co",
        "cdn-lfs-eu-1.hf.co",
        "cas-bridge.xethub.hf.co",
        "livebench.ai",
        "eqbench.com",
        "epoch.ai",
        "deepswe.datacurve.ai",
        "maker.taptap.cn",
        "www.mercor.com",
        "mercor.com",
        "www.vals.ai",
        "api.github.com",
        "raw.githubusercontent.com",
        "api.frankfurter.app",
    }
)
_HARNESS = "loop_truncated_tools_agent"
_TERMINAL_REPO = "harbor-framework/terminal-bench"
_TERMINAL_DIR = "leaderboard/submissions"


class FetchAccessDeniedError(RuntimeError):
    """External access, cancellation, request budget or allowlist denied the fetch."""


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _date(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(str(value))
        except (ValueError, TypeError):
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if isfinite(number) else None


def _ranks(scores: list[float]) -> list[int]:
    return [1 + sum(other > score for other in scores) for score in scores]


def _csv(value: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(value.lstrip("\ufeff"))))


def parse_artificial_analysis(pages: list[dict[str, Any]]) -> FetchResult:
    rows = []
    for page in pages:
        for model in page["data"]:
            score = _number(
                (model.get("evaluations") or {}).get("artificial_analysis_intelligence_index")
            )
            if score is None:
                continue
            base, descriptors = split_name(model["name"])
            name = re.sub(r"[^a-z0-9-]+", "-", model["slug"].lower())
            rows.append(
                ParsedRow(
                    name,
                    base,
                    configuration_of(descriptors),
                    "artificial-analysis:intelligence",
                    "Artificial Analysis Intelligence Index",
                    score,
                    alt_names=(model["name"],)
                    if name == model["slug"]
                    else (model["slug"], model["name"]),
                    organization=(model.get("model_creator") or {}).get("name"),
                    released_at=_date(model.get("release_date")),
                    metadata={
                        "unit": "points",
                        "sourceModelId": model["id"],
                        "sourceModelSlug": model["slug"],
                        "evaluationField": "artificial_analysis_intelligence_index",
                        "metricDirection": "HIGHER",
                    },
                )
            )
    return FetchResult(
        "artificial-analysis",
        "Artificial Analysis Intelligence Index",
        "https://artificialanalysis.ai/api/v2/language/models/free",
        "API display requires attribution; redistribution requires the provider's terms",
        "https://artificialanalysis.ai/data-api/docs",
        None,
        tuple(rows),
        {
            "apiTier": "free",
            "apiAccess": "free-headline",
            "intelligenceIndexVersion": pages[-1].get("intelligence_index_version")
            if pages
            else None,
            "sourceOperator": "Artificial Analysis",
            "sourceFamily": "broad-composite",
            "metricCount": 1,
        },
    )


def arena_configuration(name: str) -> tuple[str, Configuration]:
    base, descriptors = split_name(name)
    parts = [part.strip() for descriptor in descriptors for part in descriptor.split(",")]
    systems = tuple(part for part in parts if re.search(r"harness|agent|scaffold", part, re.I))
    tiers = [part for part in parts if part not in systems]
    base, tier = peel_tier_suffix(base)
    if tier:
        tiers.append(tier)
    config = configuration_of(tiers)
    return base, scaffolded(
        config, tuple("name-" + _slug(system) for system in systems), systems
    ) if systems else config


def parse_arena(files: dict[str, list[dict[str, Any]]], revision: str) -> tuple[FetchResult, ...]:
    out = []
    for key, name, config, category in _ARENA_BOARDS:
        records = [row for row in files[config] if row["category"] == category]
        published = max(
            (
                row["leaderboard_publish_date"]
                for row in records
                if row.get("leaderboard_publish_date")
            ),
            default=None,
        )
        rows = []
        for row in records:
            base, configuration = arena_configuration(row["model_name"])
            rows.append(
                ParsedRow(
                    row["model_name"],
                    base,
                    configuration,
                    key,
                    name,
                    float(row["rating"]),
                    key_name=_slug(row["model_name"]),
                    organization=row.get("organization"),
                    lower_bound=_number(row.get("rating_lower")),
                    upper_bound=_number(row.get("rating_upper")),
                    source_rank=row.get("rank"),
                    sample_size=round(row["vote_count"])
                    if row.get("vote_count") is not None
                    else None,
                    source_published_at=_date(row.get("leaderboard_publish_date")),
                    metadata={
                        "lowerBound": row.get("rating_lower"),
                        "upperBound": row.get("rating_upper"),
                        "arenaConfig": config,
                        "arenaCategory": category,
                        "sourceLicense": row.get("license"),
                        "originalSourceRank": row.get("rank"),
                        "metricDirection": "HIGHER",
                    },
                )
            )
        url = "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset"
        out.append(
            FetchResult(
                key,
                name,
                url,
                "CC BY 4.0",
                "https://arena.ai/leaderboard/text/creative-writing"
                if key == "arena-creative-writing"
                else url,
                _date(published),
                tuple(rows),
                {
                    "arenaConfig": config,
                    "arenaCategory": category,
                    "datasetRevision": revision,
                    "sourceOperator": "LMArena",
                    "sourceFamily": "arena-preference",
                    "metricCount": 1,
                },
            )
        )
    return tuple(out)


def parse_livebench(
    release: str, categories: dict[str, list[str]], table: str, upstream_at: str | None = None
) -> tuple[FetchResult, ...]:
    records = _csv(table)
    model_column = next(iter(records[0]), None) if records else None
    out = []
    for key, name, configured in _LIVEBENCH_BOARDS:
        cats = configured or tuple(categories)
        rows = []
        for row in records:
            model = row.get(model_column or "", "").strip()
            if not model:
                continue
            scores = []
            for category in cats:
                tasks = categories.get(category, [])
                values = tuple(_number(row.get(task)) for task in tasks)
                if tasks and all(value is not None for value in values):
                    scores.append(sum(cast(float, value) for value in values) / len(values))
            if len(scores) != len(cats) or not scores:
                continue
            base, tier = peel_effort_suffix(model)
            rows.append(
                ParsedRow(
                    model,
                    base,
                    configuration_of([tier] if tier else []),
                    key,
                    name,
                    sum(scores) / len(scores),
                    key_name=_slug(model),
                    metadata={
                        "release": release,
                        "categories": " + ".join(cats),
                        "categoryCount": len(cats),
                        "metricDirection": "HIGHER",
                        **{
                            f"livebenchCategoryScore:{category}": value
                            for category, value in zip(cats, scores, strict=True)
                        },
                    },
                )
            )
        out.append(
            FetchResult(
                key,
                name,
                "https://livebench.ai/",
                "Apache 2.0",
                "https://livebench.ai/",
                _date(upstream_at),
                tuple(rows),
                {
                    "release": release,
                    "upstreamPublishedAt": upstream_at,
                    "sourceOperator": "LiveBench",
                    "sourceFamily": "rolling-objective",
                    "metricCount": 1,
                },
            )
        )
    return tuple(out)


def epoch_configuration(version: str) -> tuple[str, Configuration]:
    base, separator, suffix = version.rpartition("_")
    if not separator or not base:
        base, suffix = version, ""
    if re.fullmatch(r"xhigh|high|medium|low|max|minimal", suffix, re.I):
        config = configuration_of([suffix.lower()])
    elif suffix.lower() == "none":
        config = configuration_of(["non-reasoning"])
    elif re.fullmatch(r"\d+k", suffix, re.I):
        config = configuration_of(["thinking-" + suffix.lower()])
    elif suffix.lower() == "promax":
        config = replace(configuration_of([]), ineligible=REASONS["special"])
    else:
        base, config = version, configuration_of([])
    if re.search(r"pre-release", version, re.I):
        config = replace(config, ineligible=REASONS["pre_release"])
    if version == "gdm-ai-co-mathematician":
        config = replace(config, ineligible=REASONS["special"])
    return base, config


def parse_epoch_archive(body: bytes) -> tuple[FetchResult, ...]:
    out = []
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        for key, name, filename, page in _EPOCH_BOARDS:
            info = archive.getinfo(filename)
            if info.file_size > 64 * 1024 * 1024:
                raise ValueError("Epoch CSV exceeds the uncompressed evidence limit")
            rows = []
            for record in _csv(archive.read(filename).decode("utf-8")):
                version, score, started = (
                    record.get("Model version", "").strip(),
                    _number(record.get("mean_score")),
                    _date(record.get("Started at")),
                )
                if not version or score is None or started is None:
                    continue
                base, config = epoch_configuration(version)
                stderr = _number(record.get("stderr"))
                rows.append(
                    ParsedRow(
                        version,
                        base,
                        config,
                        key,
                        name,
                        score,
                        key_name=_slug(version),
                        organization=record.get("Organization") or None,
                        released_at=_date(record.get("Release date")),
                        lower_bound=score - stderr if stderr is not None else None,
                        upper_bound=score + stderr if stderr is not None else None,
                        source_published_at=started,
                        metadata={
                            "stderr": stderr,
                            "runId": record.get("id") or None,
                            "metricDirection": "HIGHER",
                        },
                    )
                )
            latest = max(
                (row.source_published_at for row in rows if row.source_published_at is not None),
                default=None,
            )
            out.append(
                FetchResult(
                    key,
                    name,
                    "https://epoch.ai/data/benchmark_data.zip",
                    "CC BY 4.0 · Epoch AI own evaluations",
                    "https://epoch.ai/benchmarks/" + page,
                    latest,
                    tuple(rows),
                    {
                        "dataAtKind": "latest-evaluation",
                        "benchmarkFile": filename,
                        "scoringField": "mean_score",
                        "upstreamPublishedAt": latest.isoformat() if latest else None,
                        "attribution": "Epoch AI · AI Benchmarking Hub · CC BY 4.0",
                        "sourceOperator": "Epoch AI",
                        "metricCount": 1,
                    },
                )
            )
    return tuple(out)


def parse_deepswe(data: dict[str, Any]) -> FetchResult:
    records = data["rows"]
    ranks = _ranks([float(row["pass_rate"]) for row in records])
    rows = []
    for row, rank in zip(records, ranks, strict=True):
        system = "deepswe-v1.1:" + row["harness"]
        config = scaffolded(
            configuration_of([row["reasoning_effort"]] if row.get("reasoning_effort") else []),
            ("harness-" + _slug(row["harness"]), _slug(row["config"]), "systemid-" + _slug(system)),
            (row["harness"], system),
        )
        rows.append(
            ParsedRow(
                row["model"],
                row["model"],
                config,
                "deepswe-v1-1",
                "DeepSWE v1.1",
                float(row["pass_rate"]),
                organization=row.get("provider"),
                lower_bound=_number(row.get("ci_lo")),
                upper_bound=_number(row.get("ci_hi")),
                source_rank=rank,
                sample_size=row.get("n_attempted"),
                metadata={
                    "harness": row["harness"],
                    "ciMethod": row.get("ci_method"),
                    "runCount": row.get("n_runs"),
                    "systemId": system,
                    "taskCount": row.get("n_tasks_attempted"),
                    "meanCostUsd": row.get("mean_cost_usd"),
                    "metricDirection": "HIGHER",
                },
            )
        )
    return FetchResult(
        "deepswe-v1-1",
        "DeepSWE v1.1",
        "https://deepswe.datacurve.ai/artifacts/v1.1/leaderboard-live.json",
        "Official public results; privately observe until display terms are reviewed",
        "https://deepswe.datacurve.ai/",
        _date(data["generated_at"]),
        tuple(rows),
        {
            "harness": "mini-swe-agent",
            "comparisonSubject": "CONTROLLED_SYSTEM",
            "upstreamTaskCount": data.get("n_tasks_in_set"),
            "upstreamPublishedAt": data["generated_at"],
            "sourceOperator": "DataCurve",
            "sourceFamily": "software-engineering",
            "metricCount": 1,
        },
    )


def parse_taptap(data: dict[str, Any]) -> FetchResult:
    edition, rows = data["edition"], []
    for row in data["main_board"]:
        base = row["model"].split("@")[0]
        config = configuration_of([row["reasoning_effort"]] if row.get("reasoning_effort") else [])
        if base.lower().endswith("-contributor"):
            config = replace(config, ineligible="来源的 contributor 别名未对应到已核实的公开模型。")
        ci = row["l2"].get("ci95")
        rows.append(
            ParsedRow(
                row["model"],
                base,
                config,
                "taptap-maker",
                "TapTap Maker Benchmark",
                float(row["l2"]["rate"]),
                key_name=_slug(row["model"]),
                organization=row.get("provider"),
                lower_bound=float(ci[0]) if ci else None,
                upper_bound=float(ci[1]) if ci else None,
                source_rank=row.get("rank"),
                metadata={
                    "ciMethod": row["l2"].get("ci_method"),
                    "editionId": edition["id"],
                    "agentDriver": row.get("agent"),
                    "reasoningMode": row.get("reasoning_mode"),
                    "reasoningEffort": row.get("reasoning_effort"),
                    "costPerCaseUsd": row.get("cost_per_case_usd"),
                    "metricDirection": "HIGHER",
                },
            )
        )
    return FetchResult(
        "taptap-maker",
        "TapTap Maker Benchmark",
        "https://maker.taptap.cn/leaderboard/data/latest.json",
        "Official public results; redistribution follows TapTap terms",
        "https://maker.taptap.cn/leaderboard/",
        _date(edition["published_at"]),
        tuple(rows),
        {
            "editionId": edition["id"],
            "datasetVersion": edition["dataset_version"],
            "datasetHash": edition["dataset_hash_prefix"],
            "officialBoard": "main_board_l2",
            "upstreamPublishedAt": edition["published_at"],
            "comparisonSubject": "SYSTEM_CONFIGURATION",
            "sourceOperator": "TapTap Maker",
            "sourceFamily": "game-development",
            "metricCount": 1,
        },
    )


def _revive(value: Any) -> Any:
    if not isinstance(value, list) or len(value) != 2 or not isinstance(value[0], int):
        return value
    type_, content = value
    if type_ == 0 and isinstance(content, dict):
        return {key: _revive(item) for key, item in content.items()}
    if type_ == 1:
        return [_revive(item) for item in content]
    if type_ == 11:
        return float("inf") if content == 1 else -float("inf")
    return content


def parse_vals(markup: str) -> FetchResult:
    view = None
    for island in re.finditer(r"<astro-island\b([^>]*)>", markup):
        attributes = island[1]
        if not re.search(r'component-url="[^"]*BenchmarkView[^"]*"', attributes):
            continue
        props = re.search(r'\sprops="([^"]*)"', attributes)
        if props:
            view = _revive(json.loads(html.unescape(props[1]))["benchmarkView"])
        break
    if not isinstance(view, dict):
        raise ValueError("Vals benchmark data not found")
    published, rows = _date(view["metadata"].get("updated")), []
    for name, row in view["tasks"]["overall"].items():
        score = _number(row.get("accuracy"))
        if score is None:
            continue
        effort = (
            row.get("reasoning_effort")
            if row.get("reasoning_effort") is not None
            else row.get("compute_effort")
        )
        stderr = _number(row.get("stderr"))
        base = re.sub(r"[-_](thinking|reasoning)$", "", name.split("/")[-1], flags=re.I).replace(
            "_", "-"
        )
        rows.append(
            ParsedRow(
                name,
                base,
                configuration_of([str(effort)] if effort is not None else [], numeric_tokens=True),
                "vals-finance-agent",
                "Vals Finance Agent",
                score,
                key_name=_slug(name),
                organization=row.get("provider"),
                lower_bound=score - stderr if stderr is not None else None,
                upper_bound=score + stderr if stderr is not None else None,
                source_published_at=published,
                metadata={
                    "unit": "percent",
                    "harness": row.get("harness"),
                    "standardError": stderr,
                    "standardErrorUnit": "percentage-points",
                    "standardErrorDefinition": "reported-standard-error-of-mean",
                    "costPerTestUsd": row.get("cost_per_test"),
                    "latencySeconds": row.get("latency"),
                    "reasoningEffort": effort,
                    "metricDirection": "HIGHER",
                },
            )
        )
    page = "https://www.vals.ai/benchmarks/fabv2"
    return FetchResult(
        "vals-finance-agent",
        "Vals Finance Agent",
        page,
        "Official public results; attribution and Vals redistribution terms apply",
        page,
        published,
        tuple(rows),
        {
            "valsTask": _slug(view["metadata"]["benchmark_id"]),
            "benchmarkVersion": view["metadata"]["version"],
            "upstreamPublishedAt": view["metadata"].get("updated"),
            "upstreamModelCount": view["metadata"].get("total_models"),
            "sourceOperator": "Vals AI",
            "sourceFamily": "professional-work",
            "metricCount": 1,
        },
    )


def parse_terminal_submission(
    filename: str,
    submission: dict[str, Any],
    *,
    revision: str,
    version: str | None,
    dataset_ref: str | None,
    task_count: int | None,
) -> ParsedRow:
    source, metadata, metrics = (
        submission["source_filter"],
        submission["metadata"],
        submission["metrics"],
    )
    score = float(metrics["accuracy"])
    hw = _number(metrics.get("accuracy_ci95_half_width"))
    effort = metadata.get("reasoning_effort")
    effort = effort if effort and effort != "none" else None
    label = metadata["agent_display"]["label"] + (
        " " + source["agent_version"] if source.get("agent_version") else ""
    )
    label += " · " + (effort + " 推理" if effort else "来源未报告推理档位")
    name = source["model_name"].split("/")[-1]
    key = "tb4:" + filename
    reference = "保留模型与 Agent 的完整系统成绩供参考, 不参与综合或编程排名。"
    return ParsedRow(
        name,
        name,
        Configuration(key, label, "SCAFFOLDED", 0, 0, reference),
        "terminal-bench-4",
        "Terminal-Bench 4 · 系统参考",
        score / 100,
        configuration_key=key,
        organization=(metadata.get("model_org") or {}).get("label"),
        released_at=_date(metadata.get("date")),
        lower_bound=(score - hw) / 100 if hw is not None else None,
        upper_bound=(score + hw) / 100 if hw is not None else None,
        sample_size=task_count,
        metadata={
            "nTrials": metrics.get("n_trials"),
            "taskCount": task_count,
            "datasetRef": dataset_ref,
            "scoreField": "accuracy",
            "agentDisplay": metadata["agent_display"]["label"],
            "agentVersion": source.get("agent_version"),
            "agentFramework": source["agent"],
            "reasoningEffort": metadata.get("reasoning_effort"),
            "uncertaintyKind": "reported-ci95-half-width",
            "uncertaintyUnit": "percentage-points",
            "uncertaintyMethod": (
                "1.96 x per-task repeated-trial standard error; "
                "trial count is not independent task count"
            ),
            "benchmarkVersion": version,
            "sourceApiModelId": source["model_name"],
            "sourceSubmissionId": filename,
            "sourceSubmissionUrl": f"https://raw.githubusercontent.com/{_TERMINAL_REPO}/{revision}/{_TERMINAL_DIR}/{filename}",
            "sourceAccuracyPercent": score,
            "sourceReasoningEffort": effort,
            "sourceModelDisplayName": metadata["model_display"]["label"],
            "sourceCi95HalfWidthPercentagePoints": hw,
            "sourceDateMeaning": "model-release-date",
            "representativeMode": "CONFIGURATION_ONLY",
            "metricDirection": "HIGHER",
        },
    )


@dataclass(frozen=True, slots=True)
class ResponseData:
    body: bytes
    headers: dict[str, str]

    def text(self) -> str:
        return self.body.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.body)


RequestOutcome = Literal["succeeded", "failed", "unknown", "not_sent"]


class LeaderboardFetchClient:
    def __init__(
        self,
        *,
        allow_external_requests: bool = False,
        before_request: Callable[[int], bool] = lambda _: False,
        after_request: Callable[[int, RequestOutcome], None] = lambda _index, _outcome: None,
        cancelled: Callable[[], bool] = lambda: False,
        max_requests: int = 1000,
        max_seconds: float = 600,
        api_key: str | None = None,
        github_token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.allowed = allow_external_requests
        self._authorize, self._cancelled = before_request, cancelled
        self._settle = after_request
        self._api_key, self._github_token, self._transport = api_key, github_token, transport
        self.max_requests, self.max_seconds = max_requests, max_seconds
        if max_requests < 1 or not isfinite(max_seconds) or max_seconds <= 0:
            raise ValueError("Leaderboard transport limits must be positive and finite")
        self.requests = 0
        self._deadline: float | None = None

    def _get(
        self, url: str, *, max_bytes: int = 16 * 1024 * 1024, headers: dict[str, str] | None = None
    ) -> ResponseData:
        if not self.allowed:
            raise FetchAccessDeniedError("External leaderboard requests are disabled")
        if self._deadline is None:
            self._deadline = time.monotonic() + self.max_seconds
        request_headers = {"user-agent": "HotKey/0.1 leaderboard evidence", **(headers or {})}
        with httpx.Client(transport=self._transport, follow_redirects=False) as client:
            for _ in range(6):
                url = normalize_web_url(url, allowed_hosts=_HOSTS)
                if (
                    self._cancelled()
                    or self.requests >= self.max_requests
                    or time.monotonic() >= self._deadline
                ):
                    raise FetchAccessDeniedError("Leaderboard request cancelled or limit exhausted")
                request_index = self.requests + 1
                if not self._authorize(request_index):
                    raise FetchAccessDeniedError("Leaderboard per-request authorization denied")
                outcome: RequestOutcome = "not_sent"
                try:
                    # Durable authorization can block; recheck the deadline before transport.
                    if self._cancelled() or time.monotonic() >= self._deadline:
                        raise FetchAccessDeniedError("Leaderboard cancelled before transport")
                    self.requests += 1
                    outcome = "unknown"
                    with client.stream(
                        "GET",
                        url,
                        headers=request_headers,
                        timeout=min(120, self._deadline - time.monotonic()),
                    ) as response:
                        outcome = "failed"
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise ValueError("Leaderboard redirect is missing a location")
                            url = urljoin(url, location)
                            # Redirects never receive an API key or a GitHub token.
                            request_headers = {"user-agent": request_headers["user-agent"]}
                            outcome = "succeeded"
                            continue
                        if response.status_code != 200:
                            raise RuntimeError(f"Leaderboard upstream HTTP {response.status_code}")
                        body = bytearray()
                        for chunk in response.iter_bytes():
                            if self._cancelled() or time.monotonic() >= self._deadline:
                                raise FetchAccessDeniedError(
                                    "Leaderboard body read cancelled or timed out"
                                )
                            body.extend(chunk)
                            if len(body) > max_bytes:
                                raise ValueError("Leaderboard response exceeds evidence byte limit")
                        outcome = "succeeded"
                        return ResponseData(bytes(body), dict(response.headers))
                finally:
                    # One settlement per successful reservation, even on redirects/errors.
                    # A failing settlement aborts collection; it never retries the provider.
                    self._settle(request_index, outcome)
        raise ValueError("Leaderboard exceeded redirect limit")

    def _github(self, path: str) -> Any:
        headers = {"accept": "application/vnd.github+json"}
        if self._github_token:
            headers["authorization"] = "Bearer " + self._github_token
        return self._get(
            "https://api.github.com/" + path.lstrip("/"),
            headers=headers,
            max_bytes=32 * 1024 * 1024,
        ).json()

    def fetch_fx(self) -> dict[str, Any]:
        return cast(
            dict[str, Any], self._get("https://api.frankfurter.app/latest?from=USD&to=CNY").json()
        )

    def _head(self, repo: str, path: str | None = None) -> tuple[str, datetime | None]:
        commits = self._github(
            f"repos/{repo}/commits?per_page=1" + ("&path=" + quote(path, safe="") if path else "")
        )
        if not commits:
            raise ValueError("No data commits for benchmark repository")
        return commits[0]["sha"], _date(commits[0]["commit"]["committer"]["date"])

    def fetch(self, name: str) -> tuple[FetchResult, ...]:
        if not self.allowed:
            raise FetchAccessDeniedError("External leaderboard requests are disabled")
        if name not in SOURCE_KEYS:
            raise ValueError("Unknown benchmark collector")
        if name == "artificial-analysis":
            if not self._api_key:
                raise FetchAccessDeniedError("Artificial Analysis API key is not configured")
            pages = []
            for page_index in range(1, 21):
                data = self._get(
                    f"https://artificialanalysis.ai/api/v2/language/models/free?page={page_index}",
                    headers={"x-api-key": self._api_key, "accept": "application/json"},
                ).json()
                pages.append(data)
                if not data["pagination"]["has_more"]:
                    break
            return (parse_artificial_analysis(pages),)
        if name == "arena":
            import pyarrow.parquet as parquet  # type: ignore[import-untyped]

            dataset = "lmarena-ai/leaderboard-dataset"
            revision = self._get("https://huggingface.co/api/datasets/" + dataset).json().get("sha")
            if not revision or not re.fullmatch(r"[a-f0-9]{40,64}", revision):
                raise ValueError("Arena dataset revision is missing or invalid")
            files = {}
            for config in dict.fromkeys(board[2] for board in _ARENA_BOARDS):
                body = self._get(
                    f"https://huggingface.co/datasets/{dataset}/resolve/{revision}/{config}/latest-00000-of-00001.parquet",
                    max_bytes=64 * 1024 * 1024,
                ).body
                table = parquet.read_table(io.BytesIO(body), use_threads=False)
                if table.num_rows > 20000:
                    raise ValueError("Arena evidence exceeds row limit")
                files[config] = table.to_pylist()
            return parse_arena(files, revision)
        if name == "livebench":
            markup = self._get("https://livebench.ai/").text()
            bundle = re.search(r'src="\.?/?(static/js/main\.[a-z0-9]+\.js)"', markup)
            if not bundle:
                raise ValueError("LiveBench bundle not found")
            script = self._get("https://livebench.ai/" + bundle[1]).text()
            arrays: list[list[str]] = [
                re.findall(r"\d{4}-\d{2}-\d{2}", match[1])
                for match in re.finditer(r'\[((?:"\d{4}-\d{2}-\d{2}",?){3,})\]', script)
            ]
            if not arrays:
                raise ValueError("LiveBench release list not found")
            longest: list[str] = max(arrays, key=len)
            release = max(longest)
            tag = release.replace("-", "_")
            categories = self._get(f"https://livebench.ai/categories_{tag}.json").json()
            response = self._get(f"https://livebench.ai/table_{tag}.csv")
            return parse_livebench(
                release, categories, response.text(), response.headers.get("last-modified")
            )
        if name == "epoch":
            return parse_epoch_archive(
                self._get(
                    "https://epoch.ai/data/benchmark_data.zip", max_bytes=64 * 1024 * 1024
                ).body
            )
        if name == "deepswe":
            return (
                parse_deepswe(
                    self._get(
                        "https://deepswe.datacurve.ai/artifacts/v1.1/leaderboard-live.json"
                    ).json()
                ),
            )
        if name == "taptap":
            base = "https://maker.taptap.cn/leaderboard/data"
            pointer = self._get(base + "/latest.json").json()
            return (
                parse_taptap(
                    self._get(
                        base + "/editions/" + quote(pointer["latest"], safe="") + ".json"
                    ).json()
                ),
            )
        if name == "vals":
            return (
                parse_vals(
                    self._get(
                        "https://www.vals.ai/benchmarks/fabv2", max_bytes=32 * 1024 * 1024
                    ).text()
                ),
            )
        if name == "eqbench":
            commit, published = self._head("EQ-bench/EQ-bench-site")
            out = []
            for key, title, file, column, version, page in _EQ_BOARDS:
                script = self._get("https://eqbench.com/" + file).text()
                match = re.search(r"`\s*(model_name,[^`]+)`", script)
                if not match:
                    raise ValueError("EQ-Bench embedded CSV not found")
                records = _csv(match[1])
                if not records or column not in records[0]:
                    raise ValueError("EQ-Bench scoring column is missing")
                rows = []
                for record in records:
                    model = record.get("model_name", "").removeprefix("*").strip()
                    score = _number(record.get(column))
                    if model and score is not None:
                        rows.append(
                            ParsedRow(
                                model,
                                model.split("/")[-1],
                                configuration_of([]),
                                key,
                                title,
                                score,
                                key_name=_slug(model),
                                metadata={"benchmarkVersion": version, "metricDirection": "HIGHER"},
                            )
                        )
                out.append(
                    FetchResult(
                        key,
                        title,
                        "https://eqbench.com/" + file,
                        "MIT · EQ-bench-site README metadata declaration",
                        "https://eqbench.com/" + page,
                        published,
                        tuple(rows),
                        {
                            "dataAtKind": "score-data-commit",
                            "dataCommit": commit,
                            "upstreamPublishedAt": published.isoformat() if published else None,
                            "benchmarkVersion": version,
                            "sourceOperator": "EQ-Bench",
                            "sourceFamily": "judged-creative-writing",
                            "metricCount": 1,
                        },
                    )
                )
            return tuple(out)
        if name == "mercor":
            page = "https://www.mercor.com/apex/apex-agents-leaderboard/"
            markup = self._get(page).text()
            next_data = re.search(r'<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)</script>', markup)
            if not next_data:
                raise ValueError("Mercor page data not found")
            benchmark = json.loads(next_data[1])["props"]["pageProps"]["benchmark"]
            version_match = re.search(r"-v(\d+(?:\.\d+)*)/?$", benchmark.get("dataLink") or "")
            if not version_match:
                raise ValueError("Mercor benchmark version is not reported")
            published = None
            if benchmark.get("blogLink"):
                blog = self._get(benchmark["blogLink"]).text()
                date_match = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', blog)
                published = _date(date_match[1]) if date_match else None
            return (parse_mercor(benchmark, version_match[1], published),)
        return (self._terminal(),)

    def _terminal(self) -> FetchResult:
        head, _ = self._head(_TERMINAL_REPO)
        data_revision, published = self._head(_TERMINAL_REPO, _TERMINAL_DIR)
        files = [
            file["name"]
            for file in self._github(f"repos/{_TERMINAL_REPO}/contents/{_TERMINAL_DIR}?ref={head}")
            if file["type"] == "file" and file["name"].endswith(".json")
        ]

        def raw(path: str) -> str:
            return self._get(
                f"https://raw.githubusercontent.com/{_TERMINAL_REPO}/{head}/{path}"
            ).text()

        board, hub, checks = (
            raw("leaderboard/leaderboard.yaml"),
            raw("leaderboard/src/leaderboard/core/hub.py"),
            raw("leaderboard/src/leaderboard/ci/static_analysis.py"),
        )
        version_match = re.search(r"^name:\s*(\d+)-(\d+)-(\d+)\s*$", board, re.M)
        version = ".".join(version_match.groups()) if version_match else None
        dataset = re.search(r'^DATASET_REF\s*=\s*"([^"]+)"', hub, re.M)
        count = re.search(r"^EXPECTED_TASK_COUNT\s*=\s*(\d+)", checks, re.M)
        task_count = int(count[1]) if count else None
        rows = []
        for file in files:
            submission = json.loads(raw(_TERMINAL_DIR + "/" + quote(file, safe="")))
            if _number((submission.get("metrics") or {}).get("accuracy")) is None:
                continue
            rows.append(
                parse_terminal_submission(
                    file,
                    submission,
                    revision=head,
                    version=version,
                    dataset_ref=dataset[1] if dataset else None,
                    task_count=task_count,
                )
            )
        return FetchResult(
            "terminal-bench-4",
            "Terminal-Bench 4 · 系统参考",
            f"https://api.github.com/repos/{_TERMINAL_REPO}/contents/{_TERMINAL_DIR}",
            (
                "Apache 2.0 · Harbor / Terminal-Bench submissions, "
                "attribution and modification notices preserved"
            ),
            "https://www.tbench.ai/",
            published,
            tuple(rows),
            {
                "dataAtKind": "score-data-commit",
                "dataCommit": data_revision,
                "dataRevision": head,
                "datasetRef": dataset[1] if dataset else None,
                "benchmarkVersion": version,
                "evaluatedAt": None,
                "attribution": (
                    "Harbor / Terminal-Bench · Apache 2.0; "
                    "accuracy converted from percent to fraction; all submitted systems retained"
                ),
                "representativeMode": "CONFIGURATION_ONLY",
                "sourceDateMeaning": (
                    "metadata.date is model release date; "
                    "score publication comes from changed score content"
                ),
                "upstreamPublishedAt": published.isoformat() if published else None,
                "sourceOperator": "Harbor / Terminal-Bench",
                "sourceFamily": "terminal-agent",
                "metricCount": 0,
            },
        )


def parse_mercor(
    benchmark: dict[str, Any], version: str, published: datetime | None
) -> FetchResult:
    scored = []
    for entry in benchmark["globalLeaderboard"]:
        pass1 = next((row for row in entry["passScores"] if row["pass"] == "pass-1"), None)
        harness = (
            next(
                (row for row in pass1.get("harnessScores", []) if row["harness"] == _HARNESS), None
            )
            if pass1
            else None
        )
        if harness:
            scored.append((entry, harness))
    if len(scored) < len(benchmark["globalLeaderboard"]) / 2:
        raise ValueError("Mercor fewer than half the rows report Loop pass@1")
    system = f"{benchmark['benchmarkId']}:v{version}:{_HARNESS}"
    ranks = _ranks([float(harness["score"]) for _, harness in scored])
    rows = []
    for (entry, harness), rank in zip(scored, ranks, strict=True):
        model = entry["model"]
        effort = (model.get("effort") or "").lower()
        name = model["modelId"]
        base = (
            name[: -(len(effort) + 1)] if effort and name.lower().endswith("-" + effort) else name
        )
        config = scaffolded(
            configuration_of([effort] if effort else []),
            ("harness-" + _slug(_HARNESS), "systemid-" + _slug(system)),
            (_HARNESS, system),
        )
        score, error = float(harness["score"]), _number(harness.get("error"))
        rows.append(
            ParsedRow(
                name,
                base,
                config,
                "mercor-apex-agents:loop-pass-1",
                f"{benchmark['displayName']} {version} Pass@1 · Loop",
                score,
                key_name=_slug(name),
                organization=(model.get("provider") or {}).get("name"),
                released_at=_date(model.get("releaseDate")),
                lower_bound=score - error if error is not None else None,
                upper_bound=score + error if error is not None else None,
                source_rank=rank,
                sample_size=entry.get("nSamples"),
                source_published_at=published,
                metadata={
                    "harness": _HARNESS,
                    "systemId": system,
                    "statistic": "pass-1",
                    "reasoningEffort": model.get("effort"),
                    "reportedError": error,
                    "metricDirection": "HIGHER",
                },
            )
        )
    page = "https://www.mercor.com/apex/apex-agents-leaderboard/"
    return FetchResult(
        "mercor-apex-agents",
        f"Mercor {benchmark['displayName']} {version}",
        page,
        (
            "Official public results; data/code licenses do not imply "
            "leaderboard redistribution rights"
        ),
        page,
        published,
        tuple(rows),
        {
            "harnesses": _HARNESS,
            "statistic": "pass-1",
            "dataAtKind": "benchmark-edition-publication",
            "datasetUrl": benchmark.get("dataLink"),
            "dataDateSource": benchmark.get("blogLink"),
            "benchmarkVersion": version,
            "comparisonSubject": "CONTROLLED_SYSTEM",
            "upstreamPublishedAt": published.isoformat() if published else None,
            "sourceOperator": "Mercor",
            "sourceFamily": "professional-work",
            "metricCount": 1,
        },
    )
