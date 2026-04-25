// @ts-ignore
/* eslint-disable */
import { request } from "@/lib/request";

/** List configured content sources GET /api/sources */
export async function getSources(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: API.getSourcesParams,
  options?: import("@/lib/request").RequestOptions
) {
  return request<API.PaginatedSourceConfig>("/api/sources", {
    method: "GET",
    params: {
      // page has a default value: 1
      page: "1",
      // page_size has a default value: 20
      page_size: "20",
      ...params,
    },
    ...(options || {}),
  });
}
