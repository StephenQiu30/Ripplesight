// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 提交反馈与可选私有截图 按操作ID幂等;HMAC客户端来源持久冷却60秒。截图仅运营可读,不触发外部投递。 POST /api/feedback */
export async function submitFeedback(
  body: HotKeyAPI.FeedbackInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.FeedbackSubmissionView>("/api/feedback", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}
