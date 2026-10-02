// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 列出已确认事件 分页读取本地已确认且有可读固定成员版本的当前事件; 不触发采集或模型请求。 GET /api/events */
export async function listEvents(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listEventsParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PageViewEventReadView_>("/api/events", {
    method: "GET",
    params: {
      // limit has a default value: 20
      limit: "20",

      ...params,
    },
    ...(options || {}),
  });
}

/** 读取已确认事件 读取事件当前修订; 固定成员证据部分不可读时隐藏派生标题和摘要。 GET /api/events/${param0} */
export async function getEvent(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getEventParams,
  options?: import("@/request").RequestOptions,
) {
  const { event_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EventReadView>(`/api/events/${param0}`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 读取事件事实与直接进展 按事件修订返回事实身份、根与进展关系及固定成员版本; 不可读派生事实文本隐藏。 GET /api/events/${param0}/facts */
export async function listEventFacts(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listEventFactsParams,
  options?: import("@/request").RequestOptions,
) {
  const { event_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EventFactPageView>(`/api/events/${param0}/facts`, {
    method: "GET",
    params: {
      ...queryParams,
    },
    ...(options || {}),
  });
}

/** 读取事件独立来源热度 GET /api/events/${param0}/heat */
export async function getEventHeat(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getEventHeatParams,
  options?: import("@/request").RequestOptions,
) {
  const { event_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EventAttentionView>(`/api/events/${param0}/heat`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 读取当前事件修订的小时热度历史 读取最多7天内已有真实小时快照;每次重查固定证据与来源身份,其他修订不混入趋势。 GET /api/events/${param0}/heat-history */
export async function listEventHeatHistory(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listEventHeatHistoryParams,
  options?: import("@/request").RequestOptions,
) {
  const { event_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EventAttentionHistoryView>(
    `/api/events/${param0}/heat-history`,
    {
      method: "GET",
      params: {
        // limit has a default value: 48
        limit: "48",
        ...queryParams,
      },
      ...(options || {}),
    },
  );
}

/** 读取事件固定版本成员 按指定事件修订读取成员固定内容版本和最后一个可读观察; 代表评论单独返回最新可读评论观察, 不宣称是固定评论版本。 GET /api/events/${param0}/members */
export async function listEventMembers(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listEventMembersParams,
  options?: import("@/request").RequestOptions,
) {
  const { event_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EventMemberPageView>(
    `/api/events/${param0}/members`,
    {
      method: "GET",
      params: {
        // limit has a default value: 20
        limit: "20",
        ...queryParams,
      },
      ...(options || {}),
    },
  );
}

/** 读取有两篇独立联系证据的相关事件 固定联系报道、来源独立性及两端根事实逐项复验; 不触发关系判断或赋予正文许可。 GET /api/events/${param0}/related */
export async function listRelatedEvents(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listRelatedEventsParams,
  options?: import("@/request").RequestOptions,
) {
  const { event_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EventRelatedPageView>(
    `/api/events/${param0}/related`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 读取独立来源身份与采集时钟 GET /api/events/attention-sources */
export async function listEventAttentionSources(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.AttentionSourceView[]>(
    "/api/events/attention-sources",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}

/** 配置来源角色与独立参与者身份 按来源和精确selector创建或修改身份,已有配置要求expected_revision;不触发来源采集。 PUT /api/events/attention-sources */
export async function upsertEventAttentionSource(
  body: HotKeyAPI.AttentionSourceInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.AttentionSourceView>(
    "/api/events/attention-sources",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** 人工修订事件与事实归属 按operation_id幂等和所有影响事件的expected_revisions执行合并、拆分、移动、排除、事实合并或显式重新归组; 原修订的固定正文保留。 POST /api/events/corrections */
export async function correctEvent(
  body: HotKeyAPI.EventCorrectionInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EventCorrectionView>("/api/events/corrections", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 读取48小时独立来源热榜 重查固定版本可读性与来源角色,至少两个独立参与者且含编辑源,返回前10;趋势缺可信基线为unknown。 GET /api/events/hot */
export async function listHotEvents(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listHotEventsParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EventHotPageView>("/api/events/hot", {
    method: "GET",
    params: {
      ...params,
    },
    ...(options || {}),
  });
}
