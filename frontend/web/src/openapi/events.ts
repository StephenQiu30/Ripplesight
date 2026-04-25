// @ts-ignore
/* eslint-disable */
import { request } from "@/lib/request";

/** List hotspot events GET /api/events */
export async function getEvents(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: API.getEventsParams,
  options?: import("@/lib/request").RequestOptions
) {
  return request<API.PaginatedHotspotEvent>("/api/events", {
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

/** Get hotspot event detail GET /api/events/${param0} */
export async function getEventsEventId(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: API.getEventsEventIdParams,
  options?: import("@/lib/request").RequestOptions
) {
  const { event_id: param0, ...queryParams } = params;
  return request<API.HotspotEvent>(`/api/events/${param0}`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}
