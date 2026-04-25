// @ts-ignore
/* eslint-disable */
import { request } from "@/lib/request";

/** Search hotspot events and source summaries GET /api/search */
export async function getSearch(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: API.getSearchParams,
  options?: import("@/lib/request").RequestOptions
) {
  return request<{ items: API.HotspotEvent[]; meta: API.PageMeta }>(
    "/api/search",
    {
      method: "GET",
      params: {
        // page has a default value: 1
        page: "1",
        // page_size has a default value: 20
        page_size: "20",
        ...params,
      },
      ...(options || {}),
    }
  );
}
