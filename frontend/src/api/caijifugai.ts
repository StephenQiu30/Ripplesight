// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 列出采集覆盖窗口 按到期点倒序查询当前 owner 的持久采集事实。读取不访问来源站点。 GET /api/collection-coverage */
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

/** 读取采集覆盖窗口 按当前 owner 读取指定到期窗的执行、内容、分析和预算事实。 GET /api/collection-coverage/${param0} */
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
