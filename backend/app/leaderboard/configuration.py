"""A model's representative configuration is selected by tier, never its score.

Adapted from AIHOT fetch/configuration.ts and identity.ts under MIT.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ConfigurationKind = Literal["FIRST_PARTY", "SOURCE_DEFAULT", "SCAFFOLDED"]
REASONS = {
    "first_party": "按预先固定的规则, 采用该来源可用的最高第一方推理档位; 选择不参考跑分高低。",
    "source_default": "该来源没有区分推理档位, 采用其官方默认配置。",
    "lower_priority": "该配置已保留供核对, 但固定优先级低于本指标的代表配置。",
    "scaffolded_selected": (
        "该来源对所有模型使用同一受控系统; 按预先固定的推理档位优先级选择, "
        "配置明细保留, 成绩归到基础模型。"
    ),
    "scaffolded_lower": "该配置已保留供核对, 但固定优先级低于本指标选中的系统配置。",
    "hybrid": "混合模型或回退配置, 不能代表单个模型的能力。",
    "pre_release": "来源明确标为发布前版本, 不能代表可使用的正式模型。",
    "special": "来源为专用系统或尚未核实的运行配置, 无法归到单个公开模型。",
    "cloaked": "匿名测试时期的型号, 尚不能把该次评测对应到已公开的固定版本。",
}
_TOKEN = re.compile(
    r"^(reasoning|non-reasoning|thinking|non-thinking|adaptive-reasoning|"
    r"(x?high|medium|low|max|minimal)(-effort)?|thinking-(\d+k|minimal)|"
    r"high-\d+k|default-fallback|.+-fallback|\d+|\d+-\d+)$"
)
_TIERS = (
    (r"^max(-effort)?$", 600, "Max 推理"),
    (r"^xhigh(-effort)?$", 550, "xHigh 推理"),
    (r"^high(-effort|-\d+k)?$", 500, "High 推理"),
    (r"^medium(-effort)?$", 300, "Medium 推理"),
    (r"^low(-effort)?$", 200, "Low 推理"),
    (r"^minimal$", 100, "Minimal 推理"),
)
_CLOAKED = frozenset(
    {
        "ox-alpha",
        "horizon-alpha",
        "horizon-beta",
        "pony-alpha",
        "hunter-alpha",
        "healer-alpha",
        "optimus-alpha",
        "quasar-alpha",
        "sherlock-dash-alpha",
        "bert-nebulon-alpha",
        "sonoma-sky-alpha",
        "cypher-alpha",
        "aurora-alpha",
    }
)


@dataclass(frozen=True, slots=True)
class Configuration:
    key: str
    label: str
    kind: ConfigurationKind
    priority: int
    rank: int
    ineligible: str | None = None


def configuration_of(
    descriptors: tuple[str, ...] | list[str],
    *,
    default_kind: ConfigurationKind = "SOURCE_DEFAULT",
    numeric_tokens: bool = False,
) -> Configuration:
    tokens: set[str] = set()
    for descriptor in descriptors:
        for part in re.split(r"\s*,\s*", descriptor):
            token = re.sub(r"[^a-z0-9]+", "-", part.lower().strip()).strip("-")
            if (
                token
                and _TOKEN.fullmatch(token)
                and (numeric_tokens or not re.fullmatch(r"\d+(-\d+)?", token))
            ):
                tokens.add(token)
    for token in sorted(tokens):
        match = re.fullmatch(r"thinking-(minimal|low|medium|high)", token)
        if match:
            tokens.add(match[1])
    if "adaptive-reasoning" in tokens:
        for token in sorted(tokens):
            match = re.fullmatch(r"(x?high|medium|low)-effort", token)
            if match:
                tokens.add(match[1])
    if not tokens:
        return Configuration("source_default:default", "来源默认配置", default_kind, 400, 400)
    ordered = sorted(tokens)
    adaptive, fallback = (
        "adaptive-reasoning" in tokens,
        any(t.endswith("-fallback") for t in tokens),
    )
    priority, label = 400, "来源默认配置"
    for expression, tier, tier_label in _TIERS:
        if any(re.fullmatch(expression, token) for token in ordered):
            priority, label = tier, tier_label
            break
    if priority == 400 and tokens == {"non-reasoning"}:
        priority, label = 50, "非推理配置"
    adaptive_low = adaptive and priority in (200, 300)
    if adaptive_low:
        priority = 450
    if adaptive:
        priority += 2
        label = "自适应推理" if adaptive_low else label + " · 自适应"
    if fallback:
        priority -= 1
    budget = next(
        (
            match[1]
            for token in ordered
            if (match := re.fullmatch(r"(?:thinking|high)-(\d+k)", token))
        ),
        None,
    )
    if budget:
        label += " · " + budget
    if fallback:
        label += " · 含来源回退"
    return Configuration(
        "first_party:" + "+".join(ordered),
        label,
        "FIRST_PARTY",
        priority,
        priority,
        REASONS["hybrid"] if fallback else None,
    )


def scaffolded(
    base: Configuration, system_tokens: tuple[str, ...], system_labels: tuple[str, ...]
) -> Configuration:
    tiers = (
        base.key.removeprefix("first_party:").split("+")
        if base.key.startswith("first_party:")
        else []
    )
    key = ("scaffolded:" + "+".join(sorted([*tiers, *system_tokens])))[:108]
    label = " · ".join(
        ("完整系统" if base.kind == "SOURCE_DEFAULT" else base.label, *system_labels)
    )
    return Configuration(key, label, "SCAFFOLDED", 0, base.priority - 1, base.ineligible)


def peel_tier_suffix(name: str) -> tuple[str, str | None]:
    match = re.fullmatch(r"(.*?)-((?:x?high|medium|low|minimal|max)(?:-\d+k)?)", name, re.I)
    if match and re.match(r"^(claude|gemini|gpt-[5-9]|grok|muse)", name, re.I):
        return match[1], match[2].lower()
    return name, None


def peel_effort_suffix(name: str) -> tuple[str, str | None]:
    match = re.fullmatch(
        r"(.*?)(?:-thinking(?:-[a-z0-9]+)?)?-((?:x?high|medium|low|max|minimal)-effort)", name, re.I
    )
    return (match[1], match[2].lower()) if match else peel_tier_suffix(name)


def split_name(name: str) -> tuple[str, tuple[str, ...]]:
    match = re.fullmatch(r"(.*?)\s*\(([^()]*)\)\s*", name.strip())
    return (match[1].strip(), (match[2],)) if match else (name.strip(), ())


def model_slug(name: str) -> str:
    value = re.sub(r"([a-z])(\d)", r"\1-\2", name.lower())
    value = re.sub(r"(\d)([a-z])", r"\1-\2", value)
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def cloaked_model(*names: str | None) -> bool:
    for name in names:
        if not name:
            continue
        if re.match(r"^stealth[/_-]", name.strip(), re.I):
            return True
        slug = re.sub(r"^(?:openrouter|stealth)-", "", model_slug(name))
        slug = re.sub(r"(?:-(?:max|free))+$", "", slug)
        if slug in _CLOAKED:
            return True
    return False
