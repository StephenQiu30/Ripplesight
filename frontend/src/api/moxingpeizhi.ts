// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 读取11能力当前模型与保护catalog选择 admin→环境→默认,仅展示配置来源与server声明能力;不返回凭据、不调用模型。 GET /api/ai/models/configuration */
export async function getAiModelConfiguration(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.AiModelConfigurationView>(
    "/api/ai/models/configuration",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}

/** 按版本和原因切换单个能力模型 原运营审计与append-only模型配置版本同事务;null清admin覆盖,仅影响之后受理的任务。 PUT /api/ai/models/configuration */
export async function switchAiCapabilityModel(
  body: HotKeyAPI.AiModelSwitchInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.AiModelConfigurationView>(
    "/api/ai/models/configuration",
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

/** 人工复核一条模型超额收费并按版本恢复 POST /api/ai/models/cost-circuits/acknowledgments */
export async function acknowledgeAiCostCircuit(
  body: HotKeyAPI.AiCostCircuitAckInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.AiModelConfigurationView>(
    "/api/ai/models/cost-circuits/acknowledgments",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      data: body,
      ...(options || {}),
    },
  );
}

/** 读取原AiCall用途费用统计与模型切换审计 仅原模型账本,独立币种不换算;估计与供应商actual/cap分列,未知原调用不重复请求。 GET /api/ai/models/overview */
export async function getAiModelOverview(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getAiModelOverviewParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.AiModelOverview>("/api/ai/models/overview", {
    method: "GET",
    params: {
      // days has a default value: 7
      days: "7",
      ...params,
    },
    ...(options || {}),
  });
}
