// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 读取本人的报告邮件订阅 GET /api/notifications/email-subscription */
export async function getReportEmailSubscription(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.ReportEmailSubscriptionView>(
    "/api/notifications/email-subscription",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}

/** 设置本人的报告邮件订阅 收件人为当前已验证绑定邮箱;普通会话和CSRF,无需运营令牌;修订CAS及操作幂等。 PUT /api/notifications/email-subscription */
export async function updateReportEmailSubscription(
  body: HotKeyAPI.ReportEmailSubscriptionInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.ReportEmailSubscriptionView>(
    "/api/notifications/email-subscription",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}
