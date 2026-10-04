// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 读取六类型编辑来源配置与健康 仅运营读取。无配置返回空列表, 不创建来源、不请求外部。 GET /api/editorial-sources */
export async function listEditorialSourceProfiles(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EditorialProfileView[]>("/api/editorial-sources", {
    method: "GET",
    ...(options || {}),
  });
}

/** 创建关闭状态的编辑来源 必须先创建关闭配置, 再通过原Evidence批准来源及保留策略后启用。密钥只由服务端引用。 POST /api/editorial-sources */
export async function createEditorialSourceProfile(
  body: HotKeyAPI.EditorialProfileInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EditorialProfileView>("/api/editorial-sources", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 读取一个来源的固定配置版本 GET /api/editorial-sources/${param0} */
export async function getEditorialSourceProfile(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getEditorialSourceProfileParams,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialProfileView>(
    `/api/editorial-sources/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 按预期版本修改来源配置与启用状态 配置版本不可变; 未知外部请求须复核后才能更换配置。 PUT /api/editorial-sources/${param0} */
export async function updateEditorialSourceProfile(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.updateEditorialSourceProfileParams,
  body: HotKeyAPI.EditorialProfileInput,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialProfileView>(
    `/api/editorial-sources/${param0}`,
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

/** 批准固定来源的本机正文补全声明 审批绑定配置版本、原帖读取保存用途、零费用和固定出口证据; 不启用来源或发起请求。 POST /api/editorial-sources/${param0}/body-approval */
export async function approveEditorialBodyExtraction(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.approveEditorialBodyExtractionParams,
  body: HotKeyAPI.EditorialBodyApprovalInput,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialBodyApprovalView>(
    `/api/editorial-sources/${param0}/body-approval`,
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

/** 读取独立MEDIA许可的来源图标缓存状态 仅读取当前来源版本和Evidence,不采外源。撤权、保留许可失效与旧版本不返回图像。 GET /api/editorial-sources/${param0}/icon */
export async function getEditorialSourceIcon(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getEditorialSourceIconParams,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.SourceIconView>(
    `/api/editorial-sources/${param0}/icon`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 读取当前许可的48或96尺寸来源图标 仅读既有MinIO对象,哈希验证且读前后重新核许可,从不在GET采集。 GET /api/editorial-sources/${param0}/icon/${param1} */
export async function readEditorialSourceIcon(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.readEditorialSourceIconParams,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, mode: param1, ...queryParams } = params;
  return request<any>(`/api/editorial-sources/${param0}/icon/${param1}`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 按来源版本和理由受理图标采集 原Job/Outbox和同事务运营审计,真实外采默认关闭;unknown必须显式人工retry_unknown。 POST /api/editorial-sources/${param0}/icon/refresh */
export async function refreshEditorialSourceIcon(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.refreshEditorialSourceIconParams,
  body: HotKeyAPI.SourceIconRefreshInput,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.JobView>(
    `/api/editorial-sources/${param0}/icon/refresh`,
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

/** 接收专属令牌外部来源材料 令牌与来源绑定, 默认关闭。最多50项/4MiB, 同分区实际peer跨来源10次/滚动60秒; 许可只从当前分区Evidence批准版本读取, 材料经原Job+Outbox接收, 返回逐项回执且可GET进度。非法raw不持久, 部分拒绝不推进成功时钟。 POST /api/editorial-sources/${param0}/ingest */
export async function ingestExternalEditorialSource(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.ingestExternalEditorialSourceParams,
  body: HotKeyAPI.ExternalEditorialInput,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.ExternalIngressReceipt>(
    `/api/editorial-sources/${param0}/ingest`,
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

/** 读取专属令牌外部摄入的固定逐项回执 同来源令牌与owner校验,只读原Job/SourceRun,不返回材料正文、IP或密钥,不触发重试。 GET /api/editorial-sources/${param0}/ingest/${param1} */
export async function getExternalEditorialIngressReceipt(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getExternalEditorialIngressReceiptParams,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, run_id: param1, ...queryParams } = params;
  return request<HotKeyAPI.ExternalIngressReceipt>(
    `/api/editorial-sources/${param0}/ingest/${param1}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 按当前来源修订受理一次远端试抓 原Job与预算冻结当前修订、连接和许可; 仅试抓RSS、网页、JSON或官方X首批, 不写内容或来源水位。未知请求阻断再次受理。 POST /api/editorial-sources/${param0}/previews */
export async function previewStoredEditorialSource(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.previewStoredEditorialSourceParams,
  body: HotKeyAPI.EditorialRemotePreviewInput,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.JobView>(
    `/api/editorial-sources/${param0}/previews`,
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

/** 按固定配置和证据审批本机RSSHub入口 运营CSRF写权限、独立操作ID和当前修订/配置SHA核验。将用途、下游出口、缓存、费用和风控停止证据绑定原组件政策; 不启用来源、不批准数据许可、不发HTTP。 POST /api/editorial-sources/${param0}/rsshub-approval */
export async function approveEditorialRsshubSource(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.approveEditorialRsshubSourceParams,
  body: HotKeyAPI.EditorialRsshubApprovalInput,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialRsshubApprovalView>(
    `/api/editorial-sources/${param0}/rsshub-approval`,
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

/** 读取来源摄入与恢复状态 GET /api/editorial-sources/${param0}/runs */
export async function listEditorialSourceRuns(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listEditorialSourceRunsParams,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialRunResult[]>(
    `/api/editorial-sources/${param0}/runs`,
    {
      method: "GET",
      params: {
        // limit has a default value: 50
        limit: "50",
        ...queryParams,
      },
      ...(options || {}),
    },
  );
}

/** 人工受理一次来源采集 受理原Job与Outbox; 不在HTTP请求采集。未知请求需先人工复核。 POST /api/editorial-sources/${param0}/runs */
export async function pollEditorialSource(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.pollEditorialSourceParams,
  body: HotKeyAPI.EditorialPollInput,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.JobView>(`/api/editorial-sources/${param0}/runs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    params: { ...queryParams },
    data: body,
    ...(options || {}),
  });
}

/** 人工核验未知请求或解除已知失败 需要理由、操作ID、操作者和预期来源修订; 保留旧未知结果审计, 不自动重投。 POST /api/editorial-sources/${param0}/runs/${param1}/review */
export async function reviewEditorialSourceRun(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.reviewEditorialSourceRunParams,
  body: HotKeyAPI.EditorialRunReviewInput,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, run_id: param1, ...queryParams } = params;
  return request<HotKeyAPI.EditorialRunResult>(
    `/api/editorial-sources/${param0}/runs/${param1}/review`,
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

/** 读取原成员固定的官方 X 分组积压 仅运营读取; 不请求外部、不推进水位。返回全部原成员当前版本以供人工CAS复核。 GET /api/editorial-sources/groups/backlogs */
export async function listEditorialSourceGroupBacklogs(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EditorialGroupBacklogView[]>(
    "/api/editorial-sources/groups/backlogs",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}

/** 人工按全部原成员版本重建官方 X 分组积压 必须显式操作ID、理由、操作者和全部原成员CAS。清旧分页令牌并退回原水位, 保留旧成功时钟、同事务审计; 仅重新受理到期采集, 不在HTTP请求中调用外部。 POST /api/editorial-sources/groups/backlogs/review */
export async function reviewEditorialSourceGroupBacklog(
  body: HotKeyAPI.EditorialGroupBacklogReviewInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EditorialGroupBacklogReviewResult>(
    "/api/editorial-sources/groups/backlogs/review",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** 本地解析给定来源样本 按严格RSS、网页或JSON配置解析最多1MB给定样本; 最多返回20条元数据摘要, 不外采、不正式入库。 POST /api/editorial-sources/preview/sample */
export async function previewEditorialSourceSample(
  body: HotKeyAPI.EditorialSamplePreviewInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EditorialSourcePreviewView>(
    "/api/editorial-sources/preview/sample",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** 读取原试抓任务及有界结果 纯读取原Job和审计冻结结果; 返回条数、耗时、请求数及最多20条标题URL时间摘要, 无GET外采。 GET /api/editorial-sources/previews/${param0} */
export async function getEditorialSourcePreview(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getEditorialSourcePreviewParams,
  options?: import("@/request").RequestOptions,
) {
  const { job_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialPreviewJobView>(
    `/api/editorial-sources/previews/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 人工核对原未知试抓并允许新的显式受理 要求原试抓操作ID、当前来源修订、复核操作ID与理由。保留原unknown结果和保守预算回执, 不发HTTP、不重发原Job。 POST /api/editorial-sources/previews/${param0}/review */
export async function reviewEditorialSourcePreview(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.reviewEditorialSourcePreviewParams,
  body: HotKeyAPI.EditorialPreviewReviewInput,
  options?: import("@/request").RequestOptions,
) {
  const { job_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialPreviewReviewView>(
    `/api/editorial-sources/previews/${param0}/review`,
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
