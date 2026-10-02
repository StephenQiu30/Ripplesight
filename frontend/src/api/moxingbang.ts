// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 读取已发布模型榜 读取最近有效轮次; 筛选保留完整榜单原排名, 不触发抓取或重新计算。 GET /api/leaderboard/boards/${param0} */
export async function getLeaderboardBoard(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getLeaderboardBoardParams,
  options?: import("@/request").RequestOptions,
) {
  const { board: param0, ...queryParams } = params;
  return request<HotKeyAPI.BoardView>(`/api/leaderboard/boards/${param0}`, {
    method: "GET",
    params: {
      ...queryParams,
    },
    ...(options || {}),
  });
}

/** 读取模型证据与对比 查看公开评测、缺项、官方价格、排名稳定性及相邻模型逐项对比。 GET /api/leaderboard/models/${param0} */
export async function getLeaderboardModel(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getLeaderboardModelParams,
  options?: import("@/request").RequestOptions,
) {
  const { slug: param0, ...queryParams } = params;
  return request<HotKeyAPI.ModelDetailView>(
    `/api/leaderboard/models/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** 读取模型榜计算规则 读取算法版本、预算权重、锚点、配置政策和历史证据沿用期限。 GET /api/leaderboard/rules */
export async function getLeaderboardRules(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.RulesView>("/api/leaderboard/rules", {
    method: "GET",
    ...(options || {}),
  });
}

/** 读取榜单来源覆盖 列出来源、运营机构、权重和当前采集状态; 无发布轮次时仍可查看方法注册表。 GET /api/leaderboard/sources */
export async function listLeaderboardSources(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.SourcesView>("/api/leaderboard/sources", {
    method: "GET",
    ...(options || {}),
  });
}

/** 读取评测来源明细 读取原始分数、配置选择依据、许可、更新时间与排除原因。 GET /api/leaderboard/sources/${param0} */
export async function getLeaderboardSource(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getLeaderboardSourceParams,
  options?: import("@/request").RequestOptions,
) {
  const { source_key: param0, ...queryParams } = params;
  return request<HotKeyAPI.SourceDetailView>(
    `/api/leaderboard/sources/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}
