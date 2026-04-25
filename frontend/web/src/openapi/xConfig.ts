// @ts-ignore
/* eslint-disable */
import { request } from "@/lib/request";

/** List monitored X accounts GET /api/x/accounts */
export async function getXAccounts(
  options?: import("@/lib/request").RequestOptions
) {
  return request<{ items: API.MonitoredAccount[]; meta: API.PageMeta }>(
    "/api/x/accounts",
    {
      method: "GET",
      ...(options || {}),
    }
  );
}

/** List X keyword monitoring rules GET /api/x/keywords */
export async function getXKeywords(
  options?: import("@/lib/request").RequestOptions
) {
  return request<{ items: API.KeywordRule[]; meta: API.PageMeta }>(
    "/api/x/keywords",
    {
      method: "GET",
      ...(options || {}),
    }
  );
}
