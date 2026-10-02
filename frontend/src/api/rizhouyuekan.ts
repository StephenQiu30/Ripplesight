// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 按日周月读取最新刊期修订 GET /api/editions */
export async function listReportEditions(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listReportEditionsParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EditionSummaryView[]>("/api/editions", {
    method: "GET",
    params: {
      // kind has a default value: daily
      kind: "daily",

      // limit has a default value: 20
      limit: "20",
      ...params,
    },
    ...(options || {}),
  });
}

/** 接受完整自然刊期的冻结编选任务 POST /api/editions */
export async function requestReportEdition(
  body: HotKeyAPI.EditionRequestInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EditionDetailView>("/api/editions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 复核全部材料许可后读取刊期正文 GET /api/editions/${param0} */
export async function getReportEdition(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getReportEditionParams,
  options?: import("@/request").RequestOptions,
) {
  const { edition_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditionDetailView>(`/api/editions/${param0}`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 以版本校验保存人工修订并保留旧稿 POST /api/editions/${param0}/corrections */
export async function correctReportEdition(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.correctReportEditionParams,
  body: HotKeyAPI.EditionCorrectionInput,
  options?: import("@/request").RequestOptions,
) {
  const { edition_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditionDetailView>(
    `/api/editions/${param0}/corrections`,
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

/** 读取逐刊历史修订与当前可读状态 GET /api/editions/${param0}/revisions */
export async function listReportEditionRevisions(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listReportEditionRevisionsParams,
  options?: import("@/request").RequestOptions,
) {
  const { edition_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditionSummaryView[]>(
    `/api/editions/${param0}/revisions`,
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
