// @ts-ignore
/* eslint-disable */
import { request } from "@/lib/request";

/** Submit feedback for an event or digest POST /api/feedback */
export async function postFeedback(
  body: API.FeedbackRecord,
  options?: import("@/lib/request").RequestOptions
) {
  return request<API.FeedbackRecord>("/api/feedback", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}
