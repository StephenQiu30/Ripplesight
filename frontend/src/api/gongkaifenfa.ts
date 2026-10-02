// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** Agent接入Markdown说明 GET /agent.md */
export async function getPublicAgentMarkdown(
  options?: import("@/request").RequestOptions,
) {
  return request<string>("/agent.md", {
    method: "GET",
    ...(options || {}),
  });
}

/** 本地生成事件海报 GET /events/${param0}/poster.svg */
export async function getPublicationStoryPoster(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationStoryPosterParams,
  options?: import("@/request").RequestOptions,
) {
  const { event_id: param0, ...queryParams } = params;
  return request<string>(`/events/${param0}/poster.svg`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 精选摘要RSS GET /feed.xml */
export async function getSelectedRss(
  options?: import("@/request").RequestOptions,
) {
  return request<string>("/feed.xml", {
    method: "GET",
    ...(options || {}),
  });
}

/** 日周月刊摘要RSS GET /feed/${param0}.xml */
export async function getEditionRss(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getEditionRssParams,
  options?: import("@/request").RequestOptions,
) {
  const { kind: param0, ...queryParams } = params;
  return request<string>(`/feed/${param0}.xml`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 全部公开摘要RSS GET /feed/all.xml */
export async function getAllPublicRss(
  options?: import("@/request").RequestOptions,
) {
  return request<string>("/feed/all.xml", {
    method: "GET",
    ...(options || {}),
  });
}

/** 分类精选摘要RSS GET /feed/category/${param0}.xml */
export async function getCategoryRss(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getCategoryRssParams,
  options?: import("@/request").RequestOptions,
) {
  const { category: param0, ...queryParams } = params;
  return request<string>(`/feed/category/${param0}.xml`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 精选全文RSS 仅明确获准再分发的来源内联正文;其余仍有摘要和站内入口。 GET /feed/full.xml */
export async function getSelectedFullRss(
  options?: import("@/request").RequestOptions,
) {
  return request<string>("/feed/full.xml", {
    method: "GET",
    ...(options || {}),
  });
}

/** 分类精选全文RSS GET /feed/full/category/${param0}.xml */
export async function getCategoryFullRss(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getCategoryFullRssParams,
  options?: import("@/request").RequestOptions,
) {
  const { category: param0, ...queryParams } = params;
  return request<string>(`/feed/full/category/${param0}.xml`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 显式启用的IndexNow公开验证文件 GET /hotkey-indexnow-key.txt */
export async function getIndexNowVerification(
  options?: import("@/request").RequestOptions,
) {
  return request<string>("/hotkey-indexnow-key.txt", {
    method: "GET",
    ...(options || {}),
  });
}

/** 公开文章结构化元数据 GET /items/${param0}.jsonld */
export async function getPublicationJsonLd(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationJsonLdParams,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<string>(`/items/${param0}.jsonld`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 站内单篇Markdown GET /items/${param0}.md */
export async function getPublicationMarkdown(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationMarkdownParams,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<string>(`/items/${param0}.md`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 本地生成资讯海报 GET /items/${param0}/poster.svg */
export async function getPublicationItemPoster(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationItemPosterParams,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<string>(`/items/${param0}/poster.svg`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** Agent公开读取说明 GET /llms.txt */
export async function getPublicAgentInstructions(
  options?: import("@/request").RequestOptions,
) {
  return request<string>("/llms.txt", {
    method: "GET",
    ...(options || {}),
  });
}

/** MCP不提供SSE监听流 GET /mcp */
export async function getPublicMcpStream(
  options?: import("@/request").RequestOptions,
) {
  return request<any>("/mcp", {
    method: "GET",
    ...(options || {}),
  });
}

/** 五个只读公开MCP工具 Stateless Streamable HTTP,原生24h/7d窗口,无来源请求/模型调用/写工具。 POST /mcp */
export async function callPublicMcp(
  body: Record<string, any>,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.McpResponse>("/mcp", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 当前公开资讯分享PNG GET /og/items/${param0}.png */
export async function getPublicationItemShareImage(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationItemShareImageParams,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<string>(`/og/items/${param0}.png`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 固定公开页面分享PNG GET /og/pages/${param0}.png */
export async function getPublicPageShareImage(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicPageShareImageParams,
  options?: import("@/request").RequestOptions,
) {
  const { page: param0, ...queryParams } = params;
  return request<string>(`/og/pages/${param0}.png`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 当前公开资讯及标准二维码海报PNG GET /og/posters/${param0}.png */
export async function getPublicationItemPosterPng(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationItemPosterPngParams,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<string>(`/og/posters/${param0}.png`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 当前ALL许可日周月刊及标准二维码海报PNG GET /og/posters/reports/${param0}/${param1}.png */
export async function getPublicationEditionPosterPng(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationEditionPosterPngParams,
  options?: import("@/request").RequestOptions,
) {
  const { kind: param0, key: param1, ...queryParams } = params;
  return request<string>(`/og/posters/reports/${param0}/${param1}.png`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 当前ALL许可事件及标准二维码海报PNG GET /og/posters/stories/${param0}.png */
export async function getPublicationStoryPosterPng(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationStoryPosterPngParams,
  options?: import("@/request").RequestOptions,
) {
  const { event_id: param0, ...queryParams } = params;
  return request<string>(`/og/posters/stories/${param0}.png`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 当前ALL许可日周月刊分享PNG GET /og/reports/${param0}/${param1}.png */
export async function getPublicationEditionShareImage(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationEditionShareImageParams,
  options?: import("@/request").RequestOptions,
) {
  const { kind: param0, key: param1, ...queryParams } = params;
  return request<string>(`/og/reports/${param0}/${param1}.png`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 站点分享PNG GET /og/site.png */
export async function getPublicSiteShareImage(
  options?: import("@/request").RequestOptions,
) {
  return request<string>("/og/site.png", {
    method: "GET",
    ...(options || {}),
  });
}

/** 当前ALL许可事件分享PNG GET /og/stories/${param0}.png */
export async function getPublicationStoryShareImage(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationStoryShareImageParams,
  options?: import("@/request").RequestOptions,
) {
  const { event_id: param0, ...queryParams } = params;
  return request<string>(`/og/stories/${param0}.png`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 当前公开行业主题分享PNG GET /og/topics/${param0}.png */
export async function getPublicationTopicShareImage(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationTopicShareImageParams,
  options?: import("@/request").RequestOptions,
) {
  const { slug: param0, ...queryParams } = params;
  return request<string>(`/og/topics/${param0}.png`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 日周月刊Markdown GET /reports/${param0}/${param1}.md */
export async function getEditionMarkdown(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getEditionMarkdownParams,
  options?: import("@/request").RequestOptions,
) {
  const { kind: param0, key: param1, ...queryParams } = params;
  return request<string>(`/reports/${param0}/${param1}.md`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 本地生成日周月刊海报 GET /reports/${param0}/${param1}/poster.svg */
export async function getPublicationEditionPoster(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationEditionPosterParams,
  options?: import("@/request").RequestOptions,
) {
  const { kind: param0, key: param1, ...queryParams } = params;
  return request<string>(`/reports/${param0}/${param1}/poster.svg`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 搜索抓取策略 当前Demo默认禁止索引;显式启用后仍排除API和操作员入口。 GET /robots.txt */
export async function getPublicRobots(
  options?: import("@/request").RequestOptions,
) {
  return request<string>("/robots.txt", {
    method: "GET",
    ...(options || {}),
  });
}

/** 公开精选Markdown GET /selected.md */
export async function getSelectedMarkdown(
  options?: import("@/request").RequestOptions,
) {
  return request<string>("/selected.md", {
    method: "GET",
    ...(options || {}),
  });
}

/** 当前可索引公开文章Sitemap GET /sitemap.xml */
export async function getPublicationSitemap(
  options?: import("@/request").RequestOptions,
) {
  return request<string>("/sitemap.xml", {
    method: "GET",
    ...(options || {}),
  });
}

/** 至多五万篇固定ID分片的当前公开许可Sitemap GET /sitemaps/items-${param0}.xml */
export async function getPublicationSitemapShard(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationSitemapShardParams,
  options?: import("@/request").RequestOptions,
) {
  const { shard: param0, ...queryParams } = params;
  return request<string>(`/sitemaps/items-${param0}.xml`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 当前可索引公开刊期Sitemap分片 GET /sitemaps/reports-${param0}.xml */
export async function getPublicationEditionSitemapShard(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationEditionSitemapShardParams,
  options?: import("@/request").RequestOptions,
) {
  const { shard: param0, ...queryParams } = params;
  return request<string>(`/sitemaps/reports-${param0}.xml`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 当前可索引公开故事Sitemap分片 GET /sitemaps/stories-${param0}.xml */
export async function getPublicationStorySitemapShard(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationStorySitemapShardParams,
  options?: import("@/request").RequestOptions,
) {
  const { shard: param0, ...queryParams } = params;
  return request<string>(`/sitemaps/stories-${param0}.xml`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 当前可索引行业主题Sitemap分片 GET /sitemaps/topics-${param0}.xml */
export async function getPublicationTopicSitemapShard(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationTopicSitemapShardParams,
  options?: import("@/request").RequestOptions,
) {
  const { shard: param0, ...queryParams } = params;
  return request<string>(`/sitemaps/topics-${param0}.xml`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}
