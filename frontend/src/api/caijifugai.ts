// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 按来源与时间查询采集覆盖 从当前 owner 可访问来源的持久到期窗口分页读取任务、内容、分析与预算事实。 GET /api/collection-coverage */
export async function listCollectionCoverage(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listCollectionCoverageParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PageViewCollectionCoverageView_>(
    "/api/collection-coverage",
    {
      method: "GET",
      params: {
        // limit has a default value: 20
        limit: "20",
        ...params,
      },
      ...(options || {}),
    },
  );
}

/** 读取单个采集覆盖窗口 按当前 owner 和当前可访问来源读取窗口及其持久事实。 GET /api/collection-coverage/${param0} */
export async function getCollectionCoverage(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getCollectionCoverageParams,
  options?: import("@/request").RequestOptions,
) {
  const { window_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.CollectionCoverageView>(
    `/api/collection-coverage/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}
