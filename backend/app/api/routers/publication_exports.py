from __future__ import annotations

import hashlib
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Path, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from api.dependencies import (
    PublicationMcpServiceDependency,
    PublicationServiceDependency,
    SiteConfigurationServiceDependency,
    UserScopeDependency,
    require_identity_session,
)
from core.schemas import ErrorView
from publication.mcp_schemas import McpResponse
from publication.schemas import Category, SharePage

router = APIRouter(
    dependencies=[Depends(require_identity_session)],
    responses={401: {"model": ErrorView}},
    tags=["公开分发"],
)
_EXPORT_ERRORS: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorView, "description": "输入无效"},
    503: {"model": ErrorView, "description": "读取依赖暂不可用"},
    500: {"model": ErrorView, "description": "生成分发格式失败"},
}
_DETAIL_ERRORS = {
    **_EXPORT_ERRORS,
    404: {"model": ErrorView, "description": "内容已不可公开或不存在"},
}
_XML_RESPONSE = {
    200: {
        "content": {"application/rss+xml": {"schema": {"type": "string"}}},
        "description": "已复验公开许可的RSS 2.0",
    },
    **_EXPORT_ERRORS,
}
_PNG_RESPONSES = {
    **_DETAIL_ERRORS,
    200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}},
    304: {"description": "已复核当前许可且图片内容未变化"},
}
type ImageEtag = Annotated[str | None, Header(alias="If-None-Match", max_length=128)]


def _png(body: bytes, etag: str | None) -> Response:
    current = '"' + hashlib.sha256(body).hexdigest() + '"'
    headers = {"cache-control": "no-store", "etag": current, "x-content-type-options": "nosniff"}
    return Response(
        content=body if etag != current else None,
        status_code=200 if etag != current else 304,
        media_type="image/png" if etag != current else None,
        headers=headers,
    )


@router.get(
    "/og/site.png",
    operation_id="getPublicSiteShareImage",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="站点分享PNG",
    responses=_PNG_RESPONSES,
)
def site_share_image(
    service: PublicationServiceDependency, if_none_match: ImageEtag = None
) -> Response:
    return _png(service.share_page(), if_none_match)


@router.get(
    "/og/pages/{page}.png",
    operation_id="getPublicPageShareImage",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="固定公开页面分享PNG",
    responses=_PNG_RESPONSES,
)
def page_share_image(
    page: SharePage, service: PublicationServiceDependency, if_none_match: ImageEtag = None
) -> Response:
    return _png(service.share_page(page=page), if_none_match)


@router.get(
    "/og/items/{content_id}.png",
    operation_id="getPublicationItemShareImage",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="当前公开资讯分享PNG",
    responses=_PNG_RESPONSES,
)
def item_share_image(
    content_id: UUID,
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
    if_none_match: ImageEtag = None,
) -> Response:
    return _png(service.share_item(owner_id=owner_id, content_id=content_id), if_none_match)


@router.get(
    "/og/posters/{content_id}.png",
    operation_id="getPublicationItemPosterPng",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="当前公开资讯及标准二维码海报PNG",
    responses=_PNG_RESPONSES,
)
def item_poster_png(
    content_id: UUID,
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
    if_none_match: ImageEtag = None,
) -> Response:
    return _png(
        service.share_item(owner_id=owner_id, content_id=content_id, poster=True), if_none_match
    )


@router.get(
    "/og/stories/{event_id}.png",
    operation_id="getPublicationStoryShareImage",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="当前ALL许可事件分享PNG",
    responses=_PNG_RESPONSES,
)
def story_share_image(
    event_id: UUID,
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
    if_none_match: ImageEtag = None,
) -> Response:
    return _png(service.share_story(owner_id=owner_id, event_id=event_id), if_none_match)


@router.get(
    "/og/posters/stories/{event_id}.png",
    operation_id="getPublicationStoryPosterPng",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="当前ALL许可事件及标准二维码海报PNG",
    responses=_PNG_RESPONSES,
)
def story_poster_png(
    event_id: UUID,
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
    if_none_match: ImageEtag = None,
) -> Response:
    return _png(
        service.share_story(owner_id=owner_id, event_id=event_id, poster=True), if_none_match
    )


@router.get(
    "/og/reports/{kind}/{key}.png",
    operation_id="getPublicationEditionShareImage",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="当前ALL许可日周月刊分享PNG",
    responses=_PNG_RESPONSES,
)
def edition_share_image(
    kind: Literal["daily", "weekly", "monthly"],
    key: Annotated[str, Path(max_length=10)],
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
    if_none_match: ImageEtag = None,
) -> Response:
    return _png(service.share_edition(owner_id=owner_id, kind=kind, key=key), if_none_match)


@router.get(
    "/og/posters/reports/{kind}/{key}.png",
    operation_id="getPublicationEditionPosterPng",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="当前ALL许可日周月刊及标准二维码海报PNG",
    responses=_PNG_RESPONSES,
)
def edition_poster_png(
    kind: Literal["daily", "weekly", "monthly"],
    key: Annotated[str, Path(max_length=10)],
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
    if_none_match: ImageEtag = None,
) -> Response:
    return _png(
        service.share_edition(owner_id=owner_id, kind=kind, key=key, poster=True), if_none_match
    )


@router.get(
    "/og/topics/{slug}.png",
    operation_id="getPublicationTopicShareImage",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="当前公开行业主题分享PNG",
    responses=_PNG_RESPONSES,
)
def topic_share_image(
    slug: Annotated[str, Path(pattern=r"^[a-z0-9-]{1,80}$")],
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
    if_none_match: ImageEtag = None,
) -> Response:
    return _png(service.share_topic(owner_id=owner_id, slug=slug), if_none_match)


@router.get(
    "/hotkey-indexnow-key.txt",
    operation_id="getIndexNowVerification",
    response_model=str,
    response_class=PlainTextResponse,
    status_code=200,
    summary="显式启用的IndexNow公开验证文件",
    responses={404: {"model": ErrorView, "description": "外部索引提交未启用"}},
)
def indexnow_verification(response: Response, service: SiteConfigurationServiceDependency) -> str:
    response.headers["cache-control"] = "no-store"
    response.headers["x-content-type-options"] = "nosniff"
    return service.indexnow_verification()


def _xml(content: str, *, media_type: str = "application/rss+xml") -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"cache-control": "no-store", "x-robots-tag": "noindex, nofollow"},
    )


@router.get(
    "/feed.xml",
    operation_id="getSelectedRss",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="精选摘要RSS",
    responses=_XML_RESPONSE,
)
def selected_feed(service: PublicationServiceDependency, owner_id: UserScopeDependency) -> Response:
    return _xml(service.feed(owner_id=owner_id))


@router.get(
    "/feed/full.xml",
    operation_id="getSelectedFullRss",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="精选全文RSS",
    description="仅明确获准再分发的来源内联正文;其余仍有摘要和站内入口。",
    responses=_XML_RESPONSE,
)
def full_feed(service: PublicationServiceDependency, owner_id: UserScopeDependency) -> Response:
    return _xml(service.feed(owner_id=owner_id, kind="selected-full"))


@router.get(
    "/feed/all.xml",
    operation_id="getAllPublicRss",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="全部公开摘要RSS",
    responses=_XML_RESPONSE,
)
def all_feed(service: PublicationServiceDependency, owner_id: UserScopeDependency) -> Response:
    return _xml(service.feed(owner_id=owner_id, kind="all"))


@router.get(
    "/feed/category/{category}.xml",
    operation_id="getCategoryRss",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="分类精选摘要RSS",
    responses=_XML_RESPONSE,
)
def category_feed(
    category: Category, service: PublicationServiceDependency, owner_id: UserScopeDependency
) -> Response:
    return _xml(service.feed(owner_id=owner_id, category=category))


@router.get(
    "/feed/full/category/{category}.xml",
    operation_id="getCategoryFullRss",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="分类精选全文RSS",
    responses=_XML_RESPONSE,
)
def category_full_feed(
    category: Category, service: PublicationServiceDependency, owner_id: UserScopeDependency
) -> Response:
    return _xml(service.feed(owner_id=owner_id, category=category, kind="selected-full"))


@router.get(
    "/feed/{kind}.xml",
    operation_id="getEditionRss",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="日周月刊摘要RSS",
    responses=_XML_RESPONSE,
)
def edition_feed(
    kind: Literal["daily", "weekly", "monthly"],
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
) -> Response:
    return _xml(service.edition_feed(owner_id=owner_id, kind=kind))


@router.get(
    "/items/{content_id}.md",
    operation_id="getPublicationMarkdown",
    response_model=str,
    response_class=PlainTextResponse,
    status_code=200,
    summary="站内单篇Markdown",
    responses=_DETAIL_ERRORS,
)
def item_markdown(
    content_id: UUID,
    response: Response,
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
) -> str:
    response.headers["cache-control"] = "no-store"
    response.headers["x-robots-tag"] = "noindex, nofollow"
    return service.markdown(owner_id=owner_id, content_id=content_id)


@router.get(
    "/selected.md",
    operation_id="getSelectedMarkdown",
    response_model=str,
    response_class=PlainTextResponse,
    status_code=200,
    summary="公开精选Markdown",
    responses=_EXPORT_ERRORS,
)
def selected_markdown(
    response: Response, service: PublicationServiceDependency, owner_id: UserScopeDependency
) -> str:
    response.headers["cache-control"] = "no-store"
    response.headers["x-robots-tag"] = "noindex, nofollow"
    return service.latest_markdown(owner_id=owner_id)


@router.get(
    "/reports/{kind}/{key}.md",
    operation_id="getEditionMarkdown",
    response_model=str,
    response_class=PlainTextResponse,
    status_code=200,
    summary="日周月刊Markdown",
    responses=_DETAIL_ERRORS,
)
def edition_markdown(
    kind: Literal["daily", "weekly", "monthly"],
    key: str,
    response: Response,
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
) -> str:
    response.headers["cache-control"] = "no-store"
    response.headers["x-robots-tag"] = "noindex, nofollow"
    return service.edition_markdown(owner_id=owner_id, kind=kind, key=key)


@router.get(
    "/llms.txt",
    operation_id="getPublicAgentInstructions",
    response_model=str,
    response_class=PlainTextResponse,
    status_code=200,
    summary="Agent公开读取说明",
    responses={500: _EXPORT_ERRORS[500]},
)
def llms(response: Response, service: PublicationServiceDependency) -> str:
    response.headers["cache-control"] = "no-store"
    return service.instructions()


@router.get(
    "/agent.md",
    operation_id="getPublicAgentMarkdown",
    response_model=str,
    response_class=PlainTextResponse,
    status_code=200,
    summary="Agent接入Markdown说明",
    responses={500: _EXPORT_ERRORS[500]},
)
def agent_markdown(response: Response, service: PublicationServiceDependency) -> str:
    response.headers["cache-control"] = "no-store"
    return service.instructions()


@router.get(
    "/robots.txt",
    operation_id="getPublicRobots",
    response_model=str,
    response_class=PlainTextResponse,
    status_code=200,
    summary="搜索抓取策略",
    description="当前Demo默认禁止索引;显式启用后仍排除API和操作员入口。",
    responses={500: _EXPORT_ERRORS[500]},
)
def robots(response: Response, service: PublicationServiceDependency) -> str:
    response.headers["cache-control"] = "no-store"
    return service.robots()


@router.get(
    "/sitemap.xml",
    operation_id="getPublicationSitemap",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="当前可索引公开文章Sitemap",
    responses={
        200: {"content": {"application/xml": {"schema": {"type": "string"}}}},
        **_EXPORT_ERRORS,
    },
)
def sitemap(service: PublicationServiceDependency, owner_id: UserScopeDependency) -> Response:
    return _xml(service.sitemap(owner_id=owner_id), media_type="application/xml")


@router.get(
    "/sitemaps/items-{shard}.xml",
    operation_id="getPublicationSitemapShard",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="至多五万篇固定ID分片的当前公开许可Sitemap",
    responses={
        200: {"content": {"application/xml": {"schema": {"type": "string"}}}},
        **_DETAIL_ERRORS,
    },
)
def sitemap_shard(
    shard: Annotated[int, Path(ge=0, le=999999)],
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
) -> Response:
    return _xml(service.sitemap_shard(owner_id=owner_id, shard=shard), media_type="application/xml")


@router.get(
    "/sitemaps/stories-{shard}.xml",
    operation_id="getPublicationStorySitemapShard",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="当前可索引公开故事Sitemap分片",
    responses={
        200: {"content": {"application/xml": {"schema": {"type": "string"}}}},
        **_DETAIL_ERRORS,
    },
)
def story_sitemap_shard(
    shard: Annotated[int, Path(ge=0, le=999999)],
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
) -> Response:
    return _xml(
        service.sitemap_collection_shard(owner_id=owner_id, collection="stories", shard=shard),
        media_type="application/xml",
    )


@router.get(
    "/sitemaps/reports-{shard}.xml",
    operation_id="getPublicationEditionSitemapShard",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="当前可索引公开刊期Sitemap分片",
    responses={
        200: {"content": {"application/xml": {"schema": {"type": "string"}}}},
        **_DETAIL_ERRORS,
    },
)
def edition_sitemap_shard(
    shard: Annotated[int, Path(ge=0, le=999999)],
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
) -> Response:
    return _xml(
        service.sitemap_collection_shard(owner_id=owner_id, collection="reports", shard=shard),
        media_type="application/xml",
    )


@router.get(
    "/sitemaps/topics-{shard}.xml",
    operation_id="getPublicationTopicSitemapShard",
    response_model=None,
    response_class=Response,
    status_code=200,
    summary="当前可索引行业主题Sitemap分片",
    responses={
        200: {"content": {"application/xml": {"schema": {"type": "string"}}}},
        **_DETAIL_ERRORS,
    },
)
def topic_sitemap_shard(
    shard: Annotated[int, Path(ge=0, le=999999)],
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
) -> Response:
    return _xml(
        service.sitemap_collection_shard(owner_id=owner_id, collection="topics", shard=shard),
        media_type="application/xml",
    )


@router.get(
    "/items/{content_id}.jsonld",
    operation_id="getPublicationJsonLd",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="公开文章结构化元数据",
    responses={
        200: {"content": {"application/ld+json": {"schema": {"type": "string"}}}},
        **_DETAIL_ERRORS,
    },
)
def jsonld(
    content_id: UUID, service: PublicationServiceDependency, owner_id: UserScopeDependency
) -> Response:
    return _xml(
        service.jsonld(owner_id=owner_id, content_id=content_id), media_type="application/ld+json"
    )


@router.post(
    "/mcp",
    operation_id="callPublicMcp",
    response_model=McpResponse,
    status_code=200,
    summary="五个只读公开MCP工具",
    description="Stateless Streamable HTTP,原生24h/7d窗口,无来源请求/模型调用/写工具。",
    responses={
        202: {"description": "接受通知,无响应体"},
        400: {"model": McpResponse, "description": "JSON-RPC/Origin/协议输入无效"},
        406: {"model": McpResponse, "description": "Accept未同时声明JSON和SSE"},
        422: _EXPORT_ERRORS[422],
        503: _EXPORT_ERRORS[503],
        500: _EXPORT_ERRORS[500],
    },
)
def mcp(
    payload: Annotated[dict[str, Any], Body()],
    service: PublicationMcpServiceDependency,
    owner_id: UserScopeDependency,
    origin: Annotated[str | None, Header()] = None,
    accept: Annotated[str, Header()] = "",
    protocol: Annotated[str | None, Header(alias="MCP-Protocol-Version")] = None,
) -> Response:
    if not service.transport_allowed(origin=origin, accept=accept, protocol_version=protocol):
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid transport headers"},
            },
            status_code=406
            if "application/json" not in accept or "text/event-stream" not in accept
            else 400,
            headers={"cache-control": "no-store"},
        )
    result = service.handle(owner_id=owner_id, payload=payload)
    if result is None:
        return Response(status_code=202, headers={"cache-control": "no-store"})
    return JSONResponse(
        result.model_dump(mode="json", exclude={"result"} if result.error else {"error"}),
        status_code=400 if result.error and result.error.code == -32600 else 200,
        headers={"cache-control": "no-store", "x-robots-tag": "noindex, nofollow"},
    )


@router.get(
    "/mcp",
    operation_id="getPublicMcpStream",
    response_class=Response,
    response_model=None,
    status_code=405,
    summary="MCP不提供SSE监听流",
    responses={405: {"description": "支持POST,不提供独立SSE流"}},
)
def mcp_stream() -> Response:
    return Response(status_code=405, headers={"allow": "POST", "cache-control": "no-store"})


@router.get(
    "/items/{content_id}/poster.svg",
    operation_id="getPublicationItemPoster",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="本地生成资讯海报",
    responses={
        200: {"content": {"image/svg+xml": {"schema": {"type": "string"}}}},
        **_DETAIL_ERRORS,
    },
)
def item_poster(
    content_id: UUID, service: PublicationServiceDependency, owner_id: UserScopeDependency
) -> Response:
    return _xml(
        service.item_poster(owner_id=owner_id, content_id=content_id), media_type="image/svg+xml"
    )


@router.get(
    "/events/{event_id}/poster.svg",
    operation_id="getPublicationStoryPoster",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="本地生成事件海报",
    responses={
        200: {"content": {"image/svg+xml": {"schema": {"type": "string"}}}},
        **_DETAIL_ERRORS,
    },
)
def story_poster(
    event_id: UUID, service: PublicationServiceDependency, owner_id: UserScopeDependency
) -> Response:
    return _xml(
        service.story_poster(owner_id=owner_id, event_id=event_id), media_type="image/svg+xml"
    )


@router.get(
    "/reports/{kind}/{key}/poster.svg",
    operation_id="getPublicationEditionPoster",
    response_class=Response,
    response_model=None,
    status_code=200,
    summary="本地生成日周月刊海报",
    responses={
        200: {"content": {"image/svg+xml": {"schema": {"type": "string"}}}},
        **_DETAIL_ERRORS,
    },
)
def edition_poster(
    kind: Literal["daily", "weekly", "monthly"],
    key: str,
    service: PublicationServiceDependency,
    owner_id: UserScopeDependency,
) -> Response:
    return _xml(
        service.edition_poster(owner_id=owner_id, kind=kind, key=key), media_type="image/svg+xml"
    )
