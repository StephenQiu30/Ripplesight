"""Reader vocabulary, attribution and number formats; scoring never comes from it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from math import isfinite
from pathlib import Path
from typing import Literal

ScoreFormat = Literal["percent", "fraction", "number"]
PUBLIC_BOARDS = ("overall", "coding", "reasoning", "knowledge", "professional")
BOARD_LIMIT = 30
_PERCENT = frozenset(
    {
        "livebench-general",
        "livebench-coding",
        "livebench-reasoning",
        "livebench-writing",
        "mercor-apex-agents",
        "vals-finance-agent",
        "tau-banking",
    }
)
_PLAIN = frozenset(
    {
        "artificial-analysis",
        "artificial-analysis-multilingual",
        "arena-text",
        "arena-webdev",
        "arena-vision",
        "arena-creative-writing",
        "eq-creative",
        "eq-longform",
        "eq-emotional-v4",
    }
)
DOMESTIC_PROVIDERS = frozenset(
    {
        "alibaba",
        "deepseek",
        "moonshot",
        "xiaomi",
        "z-ai",
        "minimax",
        "baidu",
        "tencent",
        "bytedance",
        "stepfun",
        "meituan",
        "inclusionai",
        "ant-group",
        "china-mobile",
        "kuaishou",
    }
)
_DOMESTIC_NAMES = frozenset(
    {
        "alibaba",
        "deepseek",
        "moonshot ai",
        "xiaomi",
        "z.ai",
        "minimax",
        "baidu",
        "tencent",
        "bytedance",
        "stepfun",
        "meituan",
        "inclusionai",
        "ant-group",
        "china mobile",
        "kuaishou",
    }
)


@dataclass(frozen=True, slots=True)
class RegistrySource:
    key: str
    status: str
    name: str
    operator: str
    description: str
    logo: str | None
    official_url: str | None
    what: str
    usage: str
    limits: str
    license: str
    full_name: str | None = None
    area: str | None = None
    attribution: str | None = None
    components: dict[str, str] | None = None
    all_rows: bool = False


@dataclass(frozen=True, slots=True)
class RegistryGroup:
    key: str
    name: str
    blurb: str
    sources: tuple[RegistrySource, ...]


@dataclass(frozen=True, slots=True)
class RegistryLookup:
    source: RegistrySource
    group: RegistryGroup


@dataclass(frozen=True, slots=True)
class ModelAccess:
    domestic: bool
    weights_url: str | None


@dataclass(frozen=True, slots=True)
class Brand:
    src: str | None
    monogram: str
    raster: bool = False


@cache
def source_groups() -> tuple[RegistryGroup, ...]:
    raw = json.loads(Path(__file__).with_name("source-registry.json").read_text(encoding="utf-8"))
    groups: list[RegistryGroup] = []
    for group in raw["groups"]:
        sources = tuple(
            RegistrySource(
                source["key"],
                source["status"],
                source["name"],
                source["operator"],
                source["description"],
                source.get("logo"),
                source.get("officialUrl"),
                source["what"],
                source["usage"],
                source["limits"],
                source["license"],
                source.get("fullName"),
                source.get("area"),
                source.get("attribution"),
                source.get("components"),
                bool(source.get("allRows", False)),
            )
            for source in group["sources"]
        )
        groups.append(RegistryGroup(group["key"], group["name"], group["blurb"], sources))
    return tuple(groups)


def registry_source(key: str) -> RegistryLookup | None:
    return next(
        (
            RegistryLookup(source, group)
            for group in source_groups()
            for source in group.sources
            if source.key == key
        ),
        None,
    )


def source_key_of_unit(unit: str) -> str:
    return unit.partition(":")[0]


def score_format(source_key: str, sample: float | None = None) -> ScoreFormat:
    if source_key in _PERCENT:
        return "percent"
    if source_key in _PLAIN:
        return "number"
    return "fraction" if sample is not None and abs(sample) <= 1 else "number"


def format_score(value: float | None, format_: ScoreFormat) -> str:
    if value is None or not isfinite(value):
        return "—"
    if format_ == "fraction":
        return f"{value * 100:.1f}%"
    if format_ == "percent":
        return f"{value:.1f}%"
    return f"{value:,.1f}".rstrip("0").rstrip(".")


@cache
def model_weight_urls() -> dict[str, str]:
    raw = json.loads(Path(__file__).with_name("model-weights.json").read_text(encoding="utf-8"))
    return {
        slug: "https://huggingface.co/" + repository for slug, repository in raw["models"].items()
    }


def model_access(slug: str, provider_slug: str | None, provider: str | None) -> ModelAccess:
    return ModelAccess(
        provider_slug in DOMESTIC_PROVIDERS or (provider or "").strip().lower() in _DOMESTIC_NAMES,
        model_weight_urls().get(slug),
    )


def model_brand(slug: str, provider_slug: str | None, provider: str | None, name: str) -> Brand:
    label = "".join(
        c for c in (provider if provider and provider != "其他" else name) if c.isalnum()
    )
    # Only the monogram is deployed. Do not advertise upstream asset paths as local files.
    return Brand(None, label[:1].upper() or "?")


def source_brand(source: RegistrySource) -> Brand:
    label = "".join(c for c in source.operator if c.isalnum())
    return Brand(None, label[:1].upper() or "?")
