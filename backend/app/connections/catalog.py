from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, cast

from connections.catalog_schemas import (
    PublicPlatformCapability,
    PublicPlatformCapabilityView,
    PublicPlatformCatalogView,
    PublicPlatformEntryView,
    PublicPlatformQueryMode,
)
from connections.schemas import SourceConnectionAuthKind
from sources.contracts import SOCIAL_CAPABILITIES, SourceCapability


@dataclass(frozen=True, slots=True)
class SourceCatalogEntry:
    source_key: str
    display_name: str
    rollout_role: str
    product_restricted: bool
    restricted_next_action: str
    capabilities: tuple[SourceCapability, ...]
    auth_kind: SourceConnectionAuthKind


SOURCE_CATALOG = (
    *(
        SourceCatalogEntry(
            source_key=key,
            display_name=name,
            rollout_role="required",
            product_restricted=False,
            restricted_next_action="应用预设并完成真实热榜快照采集验证。",
            capabilities=(SourceCapability.HOTLIST,),
            auth_kind=SourceConnectionAuthKind.NONE,
        )
        for key, name in (
            ("hotlist_weibo", "微博热搜"),
            ("hotlist_baidu", "百度热榜"),
            ("hotlist_zhihu", "知乎热榜"),
            ("hotlist_bilibili", "B 站热门"),
            ("hotlist_36kr", "36Kr 热榜"),
            ("hotlist_thepaper", "澎湃精选"),
        )
    ),
    SourceCatalogEntry(
        source_key="bilibili",
        display_name="B 站关键词与评论",
        rollout_role="candidate",
        product_restricted=False,
        restricted_next_action="本机 MediaCrawler 登录态与持久化验收通过后人工启用。",
        capabilities=(SourceCapability.SEARCH, SourceCapability.COMMENTS),
        auth_kind=SourceConnectionAuthKind.NONE,
    ),
    SourceCatalogEntry(
        source_key="hackernews",
        display_name="Hacker News",
        rollout_role="required",
        product_restricted=False,
        restricted_next_action="应用来源预设后执行真实持久读取验证。",
        capabilities=(SourceCapability.SEARCH, SourceCapability.COMMENTS),
        auth_kind=SourceConnectionAuthKind.NONE,
    ),
    SourceCatalogEntry(
        source_key="google_news",
        display_name="Google News",
        rollout_role="required",
        product_restricted=False,
        restricted_next_action="应用来源预设后执行真实搜索 RSS 持久读取验证。",
        capabilities=(SourceCapability.SEARCH,),
        auth_kind=SourceConnectionAuthKind.NONE,
    ),
    SourceCatalogEntry(
        source_key="news_search",
        display_name="新闻网页搜索",
        rollout_role="required",
        product_restricted=False,
        restricted_next_action="启动本地 SearXNG 后执行真实新闻搜索持久读取验证。",
        capabilities=(SourceCapability.SEARCH,),
        auth_kind=SourceConnectionAuthKind.NONE,
    ),
    SourceCatalogEntry(
        source_key="rss_36kr",
        display_name="36Kr RSS",
        rollout_role="required",
        product_restricted=False,
        restricted_next_action="应用来源预设后执行真实行业 RSS 持久读取验证。",
        capabilities=(SourceCapability.SEARCH,),
        auth_kind=SourceConnectionAuthKind.NONE,
    ),
    SourceCatalogEntry(
        source_key="x",
        display_name="X",
        rollout_role="required",
        product_restricted=True,
        restricted_next_action="当前零采购约束下不启用付费 X API。请等待范围决策。",
        capabilities=SOCIAL_CAPABILITIES,
        auth_kind=SourceConnectionAuthKind.SERVER_CREDENTIAL,
    ),
    SourceCatalogEntry(
        source_key="douyin",
        display_name="抖音",
        rollout_role="candidate",
        product_restricted=False,
        restricted_next_action="确认开放平台权限、授权主体和当前准入政策后再验证。",
        capabilities=SOCIAL_CAPABILITIES,
        auth_kind=SourceConnectionAuthKind.SERVER_CREDENTIAL,
    ),
    SourceCatalogEntry(
        source_key="web",
        display_name="公开网页",
        rollout_role="required",
        product_restricted=False,
        restricted_next_action="配置明确域名范围和准入政策后执行有界读取。",
        capabilities=(SourceCapability.PAGE_CONTENT,),
        auth_kind=SourceConnectionAuthKind.NONE,
    ),
)

CAPABILITY_LABELS = {
    SourceCapability.HOTLIST: "热榜",
    SourceCapability.SEARCH: "关键词检索",
    SourceCapability.AUTHOR_POSTS: "作者作品",
    SourceCapability.COMMENTS: "评论",
    SourceCapability.REPLIES: "回复",
    SourceCapability.PAGE_CONTENT: "网页正文",
}


# A pinned source inspection, never a connection preset or runtime permission.
_RSSHUB_REVISION = "0a3a66a1cb28a645ffe90577a68411886274a2ee"
_RSSHUB_SOURCE = f"https://github.com/DIYgod/RSSHub/blob/{_RSSHUB_REVISION}/lib/routes"
_PUBLIC_CAPABILITY_LABELS = {
    PublicPlatformCapability.KEYWORD_SEARCH: "关键词检索",
    PublicPlatformCapability.AUTHOR_POSTS: "作者新帖",
    PublicPlatformCapability.INCREMENTAL: "增量与旧帖更新",
    PublicPlatformCapability.TEXT: "帖子文本",
    PublicPlatformCapability.ENGAGEMENT_COUNTS: "互动计数",
    PublicPlatformCapability.COMMENTS: "评论正文",
    PublicPlatformCapability.REPLIES: "回复及父链",
    PublicPlatformCapability.HOTLIST: "热门榜单",
    PublicPlatformCapability.HISTORY: "历史回补",
}
_COMMON_ADMISSION_REQUIREMENTS = (
    "分别确认读取、保存、站内展示、模型处理、再分发和导出用途。",
    "确认当前身份、零供应商费用、下游请求上限及可履行的删除期限。",
    "固定连接与路由版本后。经原任务验证真实材料、权限和持续窗口。",
)


def _public_entry(
    entry_key: str,
    display_name: str,
    *,
    route_template: str | None,
    status: Literal["candidate", "blocked", "excluded", "missing"],
    query_mode: str,
    object_scope: str,
    block_reason: str,
    documented: tuple[PublicPlatformCapability, ...] = (),
    limitations: tuple[str, ...] = (),
    evidence_paths: tuple[str, ...] = (),
    sort_order: str = "尚未验证。不承诺发布时间顺序。",
    pagination: str = "有限快照。未验证可信尾段。不推进完整水位。",
    fee_status: Literal["unverified", "disallowed"] = "unverified",
) -> PublicPlatformEntryView:
    return PublicPlatformEntryView(
        entry_key=entry_key,
        display_name=display_name,
        status=status,
        query_mode=cast(PublicPlatformQueryMode, query_mode),
        object_scope=object_scope,
        time_range="仅候选入口的有界返回范围。时间窗和历史深度待验证。",
        sort_order=sort_order,
        pagination=pagination,
        limitations=limitations,
        admission_requirements=_COMMON_ADMISSION_REQUIREMENTS,
        block_reason=block_reason,
        fee_status=fee_status,
        route_template=route_template,
        evidence_urls=tuple(f"{_RSSHUB_SOURCE}/{path}" for path in evidence_paths),
        capabilities=tuple(
            PublicPlatformCapabilityView(
                capability=capability,
                display_name=label,
                documented_support=(
                    ("excluded" if status == "excluded" else "route_code")
                    if capability in documented
                    else "unknown"
                ),
            )
            for capability, label in _PUBLIC_CAPABILITY_LABELS.items()
        ),
    )


def list_public_platform_catalog() -> list[PublicPlatformCatalogView]:
    """Return only pinned research; no network, secrets, database writes or admission."""
    capability = PublicPlatformCapability
    platforms: tuple[
        tuple[
            Literal["x", "instagram", "facebook", "threads", "douyin", "bilibili", "weibo"],
            str,
            tuple[PublicPlatformEntryView, ...],
        ],
        ...,
    ] = (
        (
            "x",
            "X",
            tuple(
                _public_entry(
                    f"x.{key}",
                    name,
                    route_template=route,
                    status="blocked",
                    query_mode=mode,
                    object_scope=scope,
                    documented=(supported,),
                    block_reason="当前官方路径、零付费和秘密保护条件未成立。保持零请求。",
                    limitations=(
                        "网页路径依赖认证Token。含身份轮转和敏感日志风险。",
                        "付费官方或第三方接口不进入本轮。路由存在不证明免费权益。",
                    ),
                    evidence_paths=("twitter/api/index.ts#L9", "twitter/api/web-api/utils.ts#L57"),
                    fee_status="disallowed",
                )
                for key, name, route, mode, scope, supported in (
                    (
                        "author",
                        "作者订阅流",
                        "/twitter/user/:id",
                        "author_feed",
                        "指定公开作者候选。账号身份与允许范围未验证。",
                        capability.AUTHOR_POSTS,
                    ),
                    (
                        "keyword",
                        "关键词订阅流",
                        "/twitter/keyword/:keyword",
                        "keyword_feed",
                        "关键词结果候选。不保证全站搜索或完整召回。",
                        capability.KEYWORD_SEARCH,
                    ),
                )
            ),
        ),
        (
            "instagram",
            "Instagram",
            (
                _public_entry(
                    "instagram.author",
                    "公开作者订阅流",
                    route_template="/instagram/2/user/:key",
                    status="candidate",
                    query_mode="author_feed",
                    object_scope="匿名公开作者页面候选。私密账号排除。",
                    documented=(capability.AUTHOR_POSTS, capability.TEXT),
                    block_reason="允许用途、稳定对象、登录停止及删除机制尚未验证。",
                    limitations=("页面文本候选不代表视频转写。", "无自然语言全站关键词搜索结论。"),
                    evidence_paths=("instagram/web-api/index.ts#L13",),
                ),
                _public_entry(
                    "instagram.tags",
                    "标签订阅流",
                    route_template="/instagram/2/tags/:key",
                    status="excluded",
                    query_mode="tag_feed",
                    object_scope="依赖Cookie的标签候选。首版排除。",
                    block_reason="首版不启用Cookie标签入口。",
                    limitations=("标签检索不等于自然语言关键词搜索。",),
                    evidence_paths=("instagram/web-api/index.ts#L13",),
                ),
                _public_entry(
                    "instagram.private_api",
                    "账号登录入口",
                    route_template=None,
                    status="excluded",
                    query_mode="unknown",
                    object_scope="依赖账号密码及自动登录。首版排除。",
                    block_reason="首版不启用自动登录与私有接口。",
                    evidence_paths=("instagram/private-api/index.ts#L98",),
                ),
            ),
        ),
        (
            "facebook",
            "Facebook",
            (
                _public_entry(
                    "facebook.free_entry",
                    "免费入口待确认",
                    route_template=None,
                    status="missing",
                    query_mode="unknown",
                    object_scope="目标公开作者或关键词入口尚未确认。",
                    block_reason="固定RSSHub版本中未找到对应路由。尚无可证明允许的免费路径。",
                    limitations=(
                        "仅继续核对允许的官方或发布方订阅入口。",
                        "搜索引擎索引、手动导入和自有账号不能代验公开作者订阅。",
                    ),
                ),
            ),
        ),
        (
            "threads",
            "Threads",
            (
                _public_entry(
                    "threads.author",
                    "公开作者订阅流",
                    route_template="/threads/:user",
                    status="candidate",
                    query_mode="author_feed",
                    object_scope="指定公开作者页面候选。稳定作者与帖子ID待验证。",
                    documented=(capability.AUTHOR_POSTS, capability.TEXT),
                    block_reason="数据用途、稳定身份、删除可见性和真实采集尚未验证。",
                    limitations=("页面内嵌数据有限快照不代表完整作者新帖。", "不继承官方API权限。"),
                    evidence_paths=("threads/index.ts#L11",),
                ),
                _public_entry(
                    "threads.search",
                    "标签与搜索订阅流",
                    route_template="/threads/search/:keyword",
                    status="candidate",
                    query_mode="tag_feed",
                    object_scope="页面标签/搜索结果候选。默认tags。模式须单独定标。",
                    block_reason="模式、合法空、数据用途及删除机制尚未验证。",
                    limitations=(
                        "空结果会抛错。不能当可信无更新。",
                        "标签结果不冒充公共关键词全站搜索。",
                    ),
                    evidence_paths=("threads/search.ts#L11",),
                    sort_order="default/recent分别固定。当前未验证顺序或完整性。",
                ),
            ),
        ),
        (
            "douyin",
            "抖音",
            tuple(
                _public_entry(
                    f"douyin.{key}",
                    name,
                    route_template=route,
                    status="blocked",
                    query_mode=mode,
                    object_scope=scope,
                    documented=(supported, capability.TEXT),
                    block_reason="入口依赖浏览器。当前冻结、风控停止和下游请求上限未满足。",
                    limitations=(
                        "仅初始作品列表。描述不等于字幕或整段视频摘要。",
                        "没有已确认关键词/热门路由。不扩大本人B站MediaCrawler许可。",
                    ),
                    evidence_paths=(path,),
                )
                for key, name, route, mode, scope, supported, path in (
                    (
                        "author",
                        "作者订阅流",
                        "/douyin/user/:uid",
                        "author_feed",
                        "公开UID作者页面候选。",
                        capability.AUTHOR_POSTS,
                        "douyin/user.ts#L14",
                    ),
                    (
                        "hashtag",
                        "话题订阅流",
                        "/douyin/hashtag/:cid",
                        "tag_feed",
                        "固定话题ID的初始作品列表候选。",
                        capability.TEXT,
                        "douyin/hashtag.ts#L12",
                    ),
                )
            ),
        ),
        (
            "bilibili",
            "Bilibili",
            (
                _public_entry(
                    "bilibili.popular",
                    "热门榜单",
                    route_template="/bilibili/popular/all",
                    status="candidate",
                    query_mode="hotlist",
                    object_scope="有界公开视频热门快照。非关键词或作者订阅。",
                    documented=(capability.HOTLIST, capability.TEXT),
                    block_reason="该RSS入口尚未准入。已有热门榜连接按自身证据独立判断。",
                    limitations=(
                        "标题/简介不等于视频转写。",
                        "热榜通过不关闭公开作者/关键词目标。",
                    ),
                    evidence_paths=("bilibili/popular.ts#L7",),
                ),
                _public_entry(
                    "bilibili.ranking",
                    "排行榜单",
                    route_template="/bilibili/ranking",
                    status="blocked",
                    query_mode="hotlist",
                    object_scope="公开视频排行候选。",
                    documented=(capability.HOTLIST,),
                    block_reason="部分风控会转浏览器。固定版本未见可关闭回退的路由参数。",
                    limitations=("浏览器冻结未解除。不能靠服务内置回退绕过。",),
                    evidence_paths=("bilibili/video.ts#L214",),
                ),
                _public_entry(
                    "bilibili.author",
                    "公开作者订阅流",
                    route_template="/bilibili/user/video/:uid",
                    status="blocked",
                    query_mode="author_feed",
                    object_scope="公开UP主UID作品列表候选。与本人试点分开。",
                    documented=(capability.AUTHOR_POSTS, capability.TEXT),
                    block_reason="读取失败会转浏览器。回退、身份和删除合同尚未满足。",
                    limitations=(
                        "仅按获准返回范围核对。不保证全历史。",
                        "本人试点不扩大到任意作者。",
                    ),
                    evidence_paths=("bilibili/video.ts#L214",),
                ),
                _public_entry(
                    "bilibili.keyword",
                    "关键词订阅流",
                    route_template="/bilibili/vsearch/:kw",
                    status="candidate",
                    query_mode="keyword_feed",
                    object_scope="公开视频关键词结果的单页候选。",
                    documented=(capability.KEYWORD_SEARCH, capability.TEXT),
                    block_reason="Cookie/WBI、日志、权限、请求上限及持续范围尚未验证。",
                    limitations=("单页关键词结果不能证明完整新内容水位。", "描述不冒充获准字幕。"),
                    evidence_paths=("bilibili/vsearch.ts#L9",),
                ),
                _public_entry(
                    "bilibili.comments",
                    "作品评论订阅流",
                    route_template="/bilibili/video/reply/:bvid",
                    status="candidate",
                    query_mode="comments_feed",
                    object_scope="指定BVID下评论候选。回复与父链范围未知。",
                    documented=(capability.COMMENTS,),
                    block_reason="评论字段、层级、分页、用途和旧帖更新均待独立验证。",
                    limitations=("评论数不代替评论正文。新帖扫描不代验旧帖新评论。",),
                ),
            ),
        ),
        (
            "weibo",
            "微博",
            tuple(
                _public_entry(
                    f"weibo.{key}",
                    name,
                    route_template=route,
                    status="blocked" if key != "hot" else "candidate",
                    query_mode=mode,
                    object_scope=scope,
                    documented=(supported,),
                    block_reason=(
                        "该RSS热榜入口未准入。已有微博热搜连接按自身证据独立判断。"
                        if key == "hot"
                        else "匿名Cookie自动续约阻断。固定Cookie的授权及失败停止须单独验证。"
                    ),
                    limitations=(
                        "禁止访问异常后自动续Cookie或轮换身份。",
                        "长文/转发的额外请求、分页、时间窗和删除范围须另核对。",
                        "热榜、本地主题过滤和原生关键词能力分别验收。",
                    ),
                    evidence_paths=("weibo/user.ts#L52", "weibo/utils.ts#L137"),
                )
                for key, name, route, mode, scope, supported in (
                    (
                        "hot",
                        "热门榜单",
                        "/weibo/search/hot",
                        "hotlist",
                        "微博热门话题快照。非作者新帖。",
                        capability.HOTLIST,
                    ),
                    (
                        "author",
                        "公开作者订阅流",
                        "/weibo/user/:uid",
                        "author_feed",
                        "指定公开UID的作者材料候选。",
                        capability.AUTHOR_POSTS,
                    ),
                    (
                        "keyword",
                        "关键词订阅流",
                        "/weibo/keyword/:keyword",
                        "keyword_feed",
                        "关键词结果候选。不保证全站召回。",
                        capability.KEYWORD_SEARCH,
                    ),
                )
            ),
        ),
    )
    return [
        PublicPlatformCatalogView(
            platform_key=key,
            display_name=name,
            scope_description="免费入口候选资料。执行准入、真实试点和产品可用均须独立验证。",
            inspected_revision=_RSSHUB_REVISION,
            inspected_at=date(2026, 10, 4),
            entries=entries,
        )
        for key, name, entries in platforms
    ]
