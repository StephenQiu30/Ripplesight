// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** List Alerts GET /api/alerts */
export async function listAlerts(options?: import("@/request").RequestOptions) {
  return request<HotKeyAPI.AlertRuleView[]>("/api/alerts", {
    method: "GET",
    ...(options || {}),
  });
}

/** Create Alert POST /api/alerts */
export async function createAlert(
  body: HotKeyAPI.AlertRuleInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.AlertRuleView>("/api/alerts", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** Update Alert PUT /api/alerts/${param0} */
export async function updateAlert(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.updateAlertParams,
  body: HotKeyAPI.AlertRuleInput,
  options?: import("@/request").RequestOptions,
) {
  const { rule_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.AlertRuleView>(`/api/alerts/${param0}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    params: { ...queryParams },
    data: body,
    ...(options || {}),
  });
}

/** List Alert History GET /api/alerts/${param0}/history */
export async function listAlertHistory(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listAlertHistoryParams,
  options?: import("@/request").RequestOptions,
) {
  const { rule_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.AlertEvaluationView[]>(
    `/api/alerts/${param0}/history`,
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

/** List Alert Targets GET /api/alerts/targets */
export async function listAlertTargets(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.AlertTargetView[]>("/api/alerts/targets", {
    method: "GET",
    ...(options || {}),
  });
}
