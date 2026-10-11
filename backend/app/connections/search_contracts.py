"""Explain keyword collection paths without performing I/O or granting admission."""

from pydantic import ValidationError

from connections.presets import SOURCE_PRESETS
from connections.schemas import (
    SourceConnectionConfig,
    SourceSearchConditionView,
    SourceSearchContractView,
)
from sources.adapters.rss import GOOGLE_NEWS_FEED_URL_TEMPLATE
from sources.adapters.rsshub_endpoint import is_fixed_rsshub_endpoint
from sources.adapters.web_search import SEARXNG_HOSTS

_SEED_DESCRIPTION = (
    "任一词逐个作为查询种子; 任一词为空时, 必含词空格拼接作为一个种子。"
    "排除词不发送上游。上游匹配不保证等同本地三组词规则, 本地筛选无法补回未返回的材料。"
)
_LOCAL_WINDOW = "本地按发布时间核对UTC窗口[start,end), 时间未知排除; 不向上游发送时间条件。"
_BOUNDED_WINDOW = "向上游发送UTC时间边界, 仍本地核对[start,end), 时间未知排除。"


def _conditions(
    *, seed_queries: bool, bounded_window: bool
) -> tuple[SourceSearchConditionView, ...]:
    return (
        SourceSearchConditionView(
            condition="match_any",
            handling="upstream_and_local" if seed_queries else "local_only",
            explanation=(
                "每个任一词分别召回候选; 已返回标题与文本至少命中一个, 空组不限制。"
                if seed_queries
                else "只检查快照中已返回的标题与文本, 至少命中一个, 空组不限制。"
            ),
        ),
        SourceSearchConditionView(
            condition="match_all",
            handling="local_only",
            explanation="已返回标题与文本必须命中全部必含词; 查询种子不代表上游AND, 空组不限制。",
        ),
        SourceSearchConditionView(
            condition="exclude",
            handling="local_only",
            explanation="已返回标题与文本命中任一排除词即过滤, 不发送上游NOT条件。",
        ),
        SourceSearchConditionView(
            condition="language",
            handling="local_only",
            explanation=(
                "仅按材料语言元数据筛选; 本路径不提供该元数据, "
                "指定中文/英文会排除未知, 可能全部为空。"
            ),
        ),
        SourceSearchConditionView(
            condition="window",
            handling="upstream_and_local" if bounded_window else "local_only",
            explanation=_BOUNDED_WINDOW if bounded_window else _LOCAL_WINDOW,
        ),
    )


def _unsupported(basis: str, reason: str) -> SourceSearchContractView:
    return SourceSearchContractView.model_validate(
        {
            "basis": basis,
            "path_label": "当前关键词路径不支持",
            "query_mode": "unsupported",
            "query_description": reason,
            "scope_description": "不据来源目录或历史证据推断当前可执行关键词采集。",
            "conditions": [
                {
                    "condition": condition,
                    "handling": "unsupported",
                    "explanation": "当前路径不执行此项关键词采集条件。",
                }
                for condition in ("match_any", "match_all", "exclude", "language", "window")
            ],
            "limitations": ["这是当前实现/配置边界, 不是对平台官方能力的结论。"],
        }
    )


def build_source_search_contract(
    source_key: str, config: object | None
) -> SourceSearchContractView:
    """Describe the configured path, or explicitly identify an unapplied preset.

    Args:
        source_key: Directory identity, never inferred from discovered content.
        config: Current connection configuration; None means no applied version.

    Returns:
        Read-only code-path semantics. Invalid or unimplemented configurations
        are unsupported; this does not prove admission, budget, or collection.
        Existing jobs retain their own frozen evidence and are never backfilled.
    """
    basis = "connection"
    if config is None:
        preset = SOURCE_PRESETS.get(source_key)
        if preset is None:
            return _unsupported("unconfigured", "当前目录没有已实现且准入的关键词路径。")
        config = dict(preset.config)
        basis = "preset"
    try:
        parsed = SourceConnectionConfig.model_validate(config)
    except ValidationError:
        return _unsupported(basis, "当前连接配置无法核对关键词路径, 请重新核对来源设置。")
    hosts = frozenset(parsed.allowed_hosts)
    label = ""
    scope = ""
    limitations: tuple[str, ...] = ()
    bounded = False
    seed = True
    if source_key == "hackernews" and (
        str(parsed.base_url).rstrip("/") == "https://hn.algolia.com/api/v1"
        and hosts == frozenset({"hn.algolia.com"})
    ):
        label = "Hacker News Algolia帖子索引"
        scope = "仅story索引返回的标题与文本, 不包含评论检索或链接文章全文。"
        bounded = True
        limitations = ("按索引分页和实际终止证据解释覆盖, 不保证全站召回。",)
    elif source_key == "bilibili" and hosts:
        if parsed.bilibili_transport != "chrome":
            return _unsupported(
                basis, "旧MediaCrawler搜索缺少逐请求暂停保护, 当前执行器拒绝该路径。"
            )
        label = "B站本机Chrome视频搜索"
        scope = "固定视频搜索接口, 只核对返回的视频标题和描述, 不读取视频全文。"
        bounded = True
        limitations = (
            "只取第1页最多5个候选, 最多保留2帖; 主题与来源额度可进一步收紧。",
            "先对完整查询做大小写折叠后的连续字面包含筛选; 必含词非连续出现可能被漏召回。",
        )
    elif source_key == "google_news" and (
        parsed.feed_url_template == GOOGLE_NEWS_FEED_URL_TEMPLATE
        and hosts == frozenset({"news.google.com"})
    ):
        label = "Google News查询RSS"
        scope = "仅新闻索引返回的标题和摘要, 单次RSS快照, 不代表社媒站内关键词覆盖。"
        limitations = ("固定中文地区参数不是主题语言筛选; 没有历史回补保证。",)
    elif source_key == "news_search" and (
        len(hosts) == 1
        and hosts <= SEARXNG_HOSTS
        and str(parsed.base_url).rstrip("/") == f"http://{next(iter(hosts))}:8888"
        and parsed.engines == ("duckduckgo news",)
    ):
        label = "本机SearXNG新闻搜索"
        scope = "仅指定DuckDuckGo新闻引擎返回的标题和摘要, 不代表社媒站内检索或文章全文。"
        limitations = ("搜索引擎索引与有界分页限制召回, 不保证全网覆盖。",)
    elif (
        source_key == "rss_36kr"
        and parsed.feed_url_template is not None
        and is_fixed_rsshub_endpoint(
            parsed.feed_url_template, route="/36kr/newsflashes", allowed_hosts=hosts
        )
    ):
        label = "36Kr固定快讯RSS快照"
        scope = "只读本机RSSHub的36Kr快讯快照及其标题/摘要, 不是36Kr站内关键词或全文搜索。"
        seed = False
        limitations = ("快照无历史回补保证; 多查询可能重复读取同一订阅, 再由身份去重。",)
    else:
        return _unsupported(basis, "当前地址、域名、引擎或订阅模板不对应已支持的关键词路径。")
    return SourceSearchContractView.model_validate(
        {
            "basis": basis,
            "path_label": label,
            "query_mode": "seed_queries" if seed else "feed_snapshot",
            "query_description": _SEED_DESCRIPTION
            if seed
            else "读取固定订阅, 不向上游发送关键词; 三组词仅在返回快照中本地筛选。",
            "scope_description": scope,
            "conditions": _conditions(seed_queries=seed, bounded_window=bounded),
            "limitations": limitations,
        }
    )
