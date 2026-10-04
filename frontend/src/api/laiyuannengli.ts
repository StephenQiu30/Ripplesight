// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 列出来源能力 按当前账户返回已实现来源目录、连接版本及手动/定时入口的持久状态。 GET /api/source-capabilities */
export async function listSourceCapabilities(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PageViewSourcePlatformView_>(
    "/api/source-capabilities",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}

/** 列出七平台免费入口候选 返回固定RSSHub源码核验的七平台入口、能力与阻断原因。资料声明、执行准入、真实试点和产品可用分别标记。不读取来源凭据。不创建连接或任务。不访问平台或本机采集服务。 GET /api/source-capabilities/public-platforms */
export async function listPublicPlatformCatalog(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PageViewPublicPlatformCatalogView_>(
    "/api/source-capabilities/public-platforms",
    {
      method: "GET",
      ...(options || {}),
    },
  );
}

/** 配置或启停来源连接 凭据来源只使用服务端配置; 公开网页需给出精确允许域名。版本变化后必须重新验证, 历史资料保留。 PUT /api/source-connections/${param0} */
export async function updateSourceConnection(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.updateSourceConnectionParams,
  body: HotKeyAPI.SourceConnectionUpdateInput,
  options?: import("@/request").RequestOptions,
) {
  const { source_key: param0, ...queryParams } = params;
  return request<HotKeyAPI.SourceConnectionView>(
    `/api/source-connections/${param0}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      params: { ...queryParams },
      data: body,
      ...(options || {}),
    },
  );
}
