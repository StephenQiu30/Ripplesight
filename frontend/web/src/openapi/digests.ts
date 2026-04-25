// @ts-ignore
/* eslint-disable */
import { request } from "@/lib/request";

/** Get today's digest GET /api/digests/today */
export async function getDigestsToday(
  options?: import("@/lib/request").RequestOptions
) {
  return request<API.DailyDigest>("/api/digests/today", {
    method: "GET",
    ...(options || {}),
  });
}
