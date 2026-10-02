// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 读取作品当前编辑分析与人工覆盖版本 GET /api/editorial/contents/${param0} */
export async function getCurrentEditorialRun(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getCurrentEditorialRunParams,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialRunView>(
    `/api/editorial/contents/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 受理固定正文版本的全链路编辑分析 受理与现有 Job/Outbox 同事务, 不在 HTTP 请求中调用模型。 POST /api/editorial/contents/${param0}/runs */
export async function requestEditorialRun(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.requestEditorialRunParams,
  body: HotKeyAPI.EditorialRunInput,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialRunView>(
    `/api/editorial/contents/${param0}/runs`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      params: {
        ...queryParams,
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** 读取分析结果并复核固定材料的可读权限 GET /api/editorial/runs/${param0} */
export async function getEditorialRun(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getEditorialRunParams,
  options?: import("@/request").RequestOptions,
) {
  const { run_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialRunView>(`/api/editorial/runs/${param0}`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 按人工版本纠正或清除精选、标题摘要、分类推荐理由、标签与静默覆盖 POST /api/editorial/runs/${param0}/corrections */
export async function correctEditorialRun(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.correctEditorialRunParams,
  body: HotKeyAPI.EditorialOverrideInput,
  options?: import("@/request").RequestOptions,
) {
  const { run_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialRunView>(
    `/api/editorial/runs/${param0}/corrections`,
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

/** 读取来源的编辑分析配置 GET /api/editorial/sources */
export async function listEditorialSources(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EditorialSourceView[]>("/api/editorial/sources", {
    method: "GET",
    ...(options || {}),
  });
}

/** 按版本保存来源分级、主体和编辑开关 PUT /api/editorial/sources/${param0} */
export async function saveEditorialSource(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.saveEditorialSourceParams,
  body: HotKeyAPI.EditorialSourceInput,
  options?: import("@/request").RequestOptions,
) {
  const { source_key: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialSourceView>(
    `/api/editorial/sources/${param0}`,
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
