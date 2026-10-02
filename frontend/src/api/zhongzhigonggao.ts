// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 读取重置公告监控配置 尚未配置返回 null; 读取不创建监控, 不请求 X 或模型。 GET /api/codex-resets/configuration */
export async function getCodexResetConfiguration(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.MonitorView | null>(
    "/api/codex-resets/configuration",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}

/** 配置官方重置公告监控 首次仅创建关闭配置; 修改需理由、操作ID与预期修订。 PUT /api/codex-resets/configuration */
export async function configureCodexResetMonitor(
  body: HotKeyAPI.CodexConfigurationInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.MonitorView>("/api/codex-resets/configuration", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 审计修改公告日期、类型、到账与撤回状态 日期必须显式填写; 预测不能自动确认到账, 人工确认保留receipt_review依据。 PATCH /api/codex-resets/monitors/${param0}/events/${param1} */
export async function correctCodexResetEvent(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.correctCodexResetEventParams,
  body: HotKeyAPI.CodexEventReviewInput,
  options?: import("@/request").RequestOptions,
) {
  const { monitor_id: param0, event_id: param1, ...queryParams } = params;
  return request<HotKeyAPI.ResetEventView>(
    `/api/codex-resets/monitors/${param0}/events/${param1}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      params: { ...queryParams },
      data: body,
      ...(options || {}),
    },
  );
}

/** 读取公告来源分页缺口 GET /api/codex-resets/monitors/${param0}/gaps */
export async function listCodexResetScanGaps(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listCodexResetScanGapsParams,
  options?: import("@/request").RequestOptions,
) {
  const { monitor_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.ScanGapView[]>(
    `/api/codex-resets/monitors/${param0}/gaps`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 人工核验来源缺口或允许恢复分页 保留旧查询/token; 已换配置不能重释旧token, 确认缺口不会推进verified。 POST /api/codex-resets/monitors/${param0}/gaps/${param1}/review */
export async function reviewCodexResetScanGap(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.reviewCodexResetScanGapParams,
  body: HotKeyAPI.CodexGapReviewInput,
  options?: import("@/request").RequestOptions,
) {
  const { monitor_id: param0, gap_id: param1, ...queryParams } = params;
  return request<HotKeyAPI.ScanGapView>(
    `/api/codex-resets/monitors/${param0}/gaps/${param1}/review`,
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

/** 审计修正公告帖子归属 来源公告与目标公告分别校验修订; 空目标仅解除现有归属, 保留原帖及审计。 POST /api/codex-resets/monitors/${param0}/posts/${param1}/relink */
export async function relinkCodexResetPost(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.relinkCodexResetPostParams,
  body: HotKeyAPI.CodexPostRelinkInput,
  options?: import("@/request").RequestOptions,
) {
  const { monitor_id: param0, post_id: param1, ...queryParams } = params;
  return request<HotKeyAPI.ResetPostView>(
    `/api/codex-resets/monitors/${param0}/posts/${param1}/relink`,
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

/** 复核公告帖子或明确允许再次识别 未知模型请求不得自动重付; retry需理由、操作ID与帖子复核版本。 POST /api/codex-resets/monitors/${param0}/posts/${param1}/review */
export async function reviewCodexResetPost(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.reviewCodexResetPostParams,
  body: HotKeyAPI.CodexPostReviewInput,
  options?: import("@/request").RequestOptions,
) {
  const { monitor_id: param0, post_id: param1, ...queryParams } = params;
  return request<HotKeyAPI.ResetPostView>(
    `/api/codex-resets/monitors/${param0}/posts/${param1}/review`,
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

/** 人工受理一次官方公告扫描 受理唯一Job/Outbox; 不在HTTP请求中采集, 未知来源请求必须先复核。 POST /api/codex-resets/monitors/${param0}/ticks */
export async function pollCodexResetMonitor(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.pollCodexResetMonitorParams,
  body: HotKeyAPI.CodexTickInput,
  options?: import("@/request").RequestOptions,
) {
  const { monitor_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.JobView>(
    `/api/codex-resets/monitors/${param0}/ticks`,
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

/** 读取公告源帖子 分页读取持久帖子及复核状态, 每页至多50条; 未配置为零条且配置查询为 null。 GET /api/codex-resets/posts */
export async function listCodexResetPosts(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listCodexResetPostsParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.ResetPostView[]>("/api/codex-resets/posts", {
    method: "GET",
    params: {
      // page has a default value: 1
      page: "1",
      // filter_key has a default value: all
      filter_key: "all",
      ...params,
    },
    ...(options || {}),
  });
}

/** 读取最近公告与确认轮次 按北京时间保留最近七日公告上下文, 未配置返回 null, 不触发扫描。 GET /api/codex-resets/recent */
export async function getRecentCodexResets(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.ResetSnapshot | null>("/api/codex-resets/recent", {
    method: "GET",
    ...(options || {}),
  });
}

/** 读取公告日历与健康状态 返回持久源公告与程序状态; 预测不表示确认到账, 未配置返回 null。 GET /api/codex-resets/snapshot */
export async function getCodexResetSnapshot(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getCodexResetSnapshotParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.ResetSnapshot | null>("/api/codex-resets/snapshot", {
    method: "GET",
    params: {
      ...params,
    },
    ...(options || {}),
  });
}

/** 读取公告快照版本 轻量读取同一快照版本, 便于客户端刷新判断; 未配置返回 null。 GET /api/codex-resets/version */
export async function getCodexResetVersion(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.ResetVersionView | null>(
    "/api/codex-resets/version",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}
