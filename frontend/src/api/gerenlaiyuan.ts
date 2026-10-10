// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** List Personal Sources GET /api/sources/personal */
export async function listPersonalSources(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EditorialProfileView[]>("/api/sources/personal", {
    method: "GET",
    ...(options || {}),
  });
}

/** Create Personal Source POST /api/sources/personal */
export async function createPersonalSource(
  body: HotKeyAPI.PersonalSourceInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.EditorialProfileView>("/api/sources/personal", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** Update Personal Source PUT /api/sources/personal/${param0} */
export async function updatePersonalSource(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.updatePersonalSourceParams,
  body: HotKeyAPI.PersonalSourceInput,
  options?: import("@/request").RequestOptions,
) {
  const { profile_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.EditorialProfileView>(
    `/api/sources/personal/${param0}`,
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
