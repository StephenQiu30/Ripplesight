// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 读取当前可公开刊期与完整引用 日周月刊只读出口;当前修订及全部冻结参考逐次复验,不回退旧修订或生成报告。 GET /api/publication/editions/${param0}/${param1} */
export async function getPublicEdition(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicEditionParams,
  options?: import("@/request").RequestOptions,
) {
  const { kind: param0, key: param1, ...queryParams } = params;
  return request<HotKeyAPI.PublicEditionView>(
    `/api/publication/editions/${param0}/${param1}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 同事实的当前公开报道及修订分页 GET /api/publication/facts/${param0}/reports */
export async function getPublicFactReports(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicFactReportsParams,
  options?: import("@/request").RequestOptions,
) {
  const { fact_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.PublicFactReportsPage>(
    `/api/publication/facts/${param0}/reports`,
    {
      method: "GET",
      params: {
        // limit has a default value: 20
        limit: "20",

        // window has a default value: 24h
        window: "24h",
        // channel has a default value: all
        channel: "all",

        ...queryParams,
      },
      ...(options || {}),
    },
  );
}

/** 读取公开事件热榜 48小时来源热度排序,至少两个参与方且含编辑来源;全部固定材料必须可公开。 GET /api/publication/hot */
export async function getPublicHotStories(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicHotStoriesParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PublicStoriesPage>("/api/publication/hot", {
    method: "GET",
    params: {
      // limit has a default value: 10
      limit: "10",
      ...params,
    },
    ...(options || {}),
  });
}

/** 读取公开资讯 24小时或7天原生窗口;所有出口复验相同固定版本和许可。GET不采集或调用模型。 GET /api/publication/items */
export async function listPublicItems(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listPublicItemsParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PublicItemsPage>("/api/publication/items", {
    method: "GET",
    params: {
      // window has a default value: 24h
      window: "24h",
      // mode has a default value: selected
      mode: "selected",
      // by has a default value: timeline
      by: "timeline",

      // search_order has a default value: relevance
      search_order: "relevance",
      // limit has a default value: 50
      limit: "50",
      ...params,
    },
    ...(options || {}),
  });
}

/** 读取可再分发的发布详情 仅有明确再分发许可时包含正文;其余保留摘要和站内入口。 GET /api/publication/items/${param0} */
export async function getPublicPublicationItem(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicPublicationItemParams,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.PublicItemDetailView>(
    `/api/publication/items/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 人工调整公开范围与索引 明确预期修订,支持公开/摘要/撤回及SEO索引/排除;修改留审计回执。 PUT /api/publication/items/${param0}/override */
export async function overridePublication(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.overridePublicationParams,
  body: HotKeyAPI.PublicationOverrideInput,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.PublishResultView>(
    `/api/publication/items/${param0}/override`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      params: { ...queryParams },
      data: body,
      ...(options || {}),
    },
  );
}

/** 读取站内发布正文 站内全文许可与再分发许可分别判断;摘要模式不含正文、理由和归组信息。 GET /api/publication/items/${param0}/site */
export async function getSitePublicationItem(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getSitePublicationItemParams,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.PublicItemDetailView>(
    `/api/publication/items/${param0}/site`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 读取公开来源许可策略 GET /api/publication/policies */
export async function listPublicationPolicies(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.SourcePolicyView[]>("/api/publication/policies", {
    method: "GET",
    ...(options || {}),
  });
}

/** 读取公开投影重建进度 GET /api/publication/republish/${param0} */
export async function getPublicationRepublishRun(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationRepublishRunParams,
  options?: import("@/request").RequestOptions,
) {
  const { run_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.RepublishRunView>(
    `/api/publication/republish/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 读取精选增量修订 保留每个序号;已限制/撤回的历史upsert只输出remove,防离线重放泄漏。 GET /api/publication/selected/changes */
export async function getSelectedPublicationChanges(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getSelectedPublicationChangesParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.SelectedChangesPage>(
    "/api/publication/selected/changes",
    {
      method: "GET",
      params: {
        // limit has a default value: 100
        limit: "100",
        ...params,
      },
      ...(options || {}),
    },
  );
}

/** 读取全量精选同步快照 全量快照不限于7天;水位不能越过仍等待公开的条目。 GET /api/publication/selected/snapshot */
export async function getSelectedPublicationSnapshot(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getSelectedPublicationSnapshotParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.SelectedSnapshotView>(
    "/api/publication/selected/snapshot",
    {
      method: "GET",
      params: {
        // limit has a default value: 100
        limit: "100",
        ...params,
      },
      ...(options || {}),
    },
  );
}

/** 修订来源公开许可 操作员令牌及写入头必需;默认关闭全文/再分发/索引许可,留存不可变修订回执。 PUT /api/publication/sources/${param0}/policy */
export async function savePublicationSourcePolicy(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.savePublicationSourcePolicyParams,
  body: HotKeyAPI.SourcePolicyInput,
  options?: import("@/request").RequestOptions,
) {
  const { source_key: param0, ...queryParams } = params;
  return request<HotKeyAPI.SourcePolicyView>(
    `/api/publication/sources/${param0}/policy`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      params: { ...queryParams },
      data: body,
      ...(options || {}),
    },
  );
}

/** 受理来源公开投影重建 既有jobs/Outbox原子受理,分批持久游标且支持取消/恢复,不重新请求来源或模型。 POST /api/publication/sources/${param0}/republish */
export async function republishPublicationSource(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.republishPublicationSourceParams,
  body: HotKeyAPI.RepublishInput,
  options?: import("@/request").RequestOptions,
) {
  const { source_key: param0, ...queryParams } = params;
  return request<HotKeyAPI.RepublishRunView>(
    `/api/publication/sources/${param0}/republish`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      params: { ...queryParams },
      data: body,
      ...(options || {}),
    },
  );
}

/** 读取公开事件故事 事件摘要与直接进展按全部固定成员许可复验,不从不可公开成员保留派生文本。 GET /api/publication/stories/${param0} */
export async function getPublicStory(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicStoryParams,
  options?: import("@/request").RequestOptions,
) {
  const { event_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.PublicStoryView>(
    `/api/publication/stories/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 故事中的独立发生事实和精选进展 GET /api/publication/stories/${param0}/developments */
export async function getPublicStoryDevelopments(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicStoryDevelopmentsParams,
  options?: import("@/request").RequestOptions,
) {
  const { event_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.PublicDevelopmentsPage>(
    `/api/publication/stories/${param0}/developments`,
    {
      method: "GET",
      params: {
        // limit has a default value: 20
        limit: "20",

        // window has a default value: 24h
        window: "24h",
        // channel has a default value: all
        channel: "all",

        ...queryParams,
      },
      ...(options || {}),
    },
  );
}

/** 按事件与事实折叠的精选阅读时间线 GET /api/publication/timeline */
export async function getPublicReadingTimeline(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicReadingTimelineParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PublicTimelinePage>("/api/publication/timeline", {
    method: "GET",
    params: {
      // limit has a default value: 20
      limit: "20",

      // window has a default value: 24h
      window: "24h",
      // channel has a default value: all
      channel: "all",

      ...params,
    },
    ...(options || {}),
  });
}

/** 公开行业专题目录与当前许可统计 GET /api/publication/topics */
export async function getPublicTopicDirectory(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PublicTopicDirectoryView>(
    "/api/publication/topics",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}

/** 公开专题固定二十条分页 GET /api/publication/topics/${param0} */
export async function getPublicTopicPage(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicTopicPageParams,
  options?: import("@/request").RequestOptions,
) {
  const { slug: param0, ...queryParams } = params;
  return request<HotKeyAPI.PublicTopicPageView>(
    `/api/publication/topics/${param0}`,
    {
      method: "GET",
      params: {
        // page has a default value: 1
        page: "1",
        ...queryParams,
      },
      ...(options || {}),
    },
  );
}
