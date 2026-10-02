// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 连续分页读取当前可公开刊物历史 只列最新修订且全部冻结参考仍获许可的已完成刊物;不回退旧稿或生成报告。 GET /api/publication/catalogue/editions */
export async function listPublicEditionCatalogue(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listPublicEditionCatalogueParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PublicEditionCatalogueView>(
    "/api/publication/catalogue/editions",
    {
      method: "GET",
      params: {
        // kind has a default value: daily
        kind: "daily",

        // limit has a default value: 20
        limit: "20",
        ...params,
      },
      ...(options || {}),
    },
  );
}

/** 读取刊期及前后可公开刊物 逐刊复核当前修订、全部材料与许可;缺刊不会自动换到其他日期。 GET /api/publication/catalogue/editions/${param0}/navigation/${param1} */
export async function getPublicEditionNavigation(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicEditionNavigationParams,
  options?: import("@/request").RequestOptions,
) {
  const { kind: param0, key: param1, ...queryParams } = params;
  return request<HotKeyAPI.PublicEditionNavigationView>(
    `/api/publication/catalogue/editions/${param0}/navigation/${param1}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 读取指定北京月份的已公开日报日历 只列当月真实可读刊期;缺刊与撤回日保持空白,不构造标题或正文。 GET /api/publication/catalogue/editions/daily/months/${param0} */
export async function getPublicDailyCalendar(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicDailyCalendarParams,
  options?: import("@/request").RequestOptions,
) {
  const { month: param0, ...queryParams } = params;
  return request<HotKeyAPI.PublicDailyCalendarView>(
    `/api/publication/catalogue/editions/daily/months/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}
