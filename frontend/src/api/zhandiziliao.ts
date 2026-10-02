// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 读取独立运营站点设置 GET /api/operations/site */
export async function getOperatorSiteConfiguration(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.SiteConfigurationView>("/api/operations/site", {
    method: "GET",
    ...(options || {}),
  });
}

/** 保存联系资料与二维码 运营凭据/CSRF、原因、版本CAS与operation_id幂等;图片限2MiB,解码验证后规范PNG。 PUT /api/operations/site */
export async function saveOperatorSiteConfiguration(
  body: HotKeyAPI.SiteConfigurationInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.SiteConfigurationView>("/api/operations/site", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 已启用的公开联系资料 GET /api/site/contact */
export async function getPublicContact(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PublicContactView>("/api/site/contact", {
    method: "GET",
    ...(options || {}),
  });
}

/** 当前启用且哈希匹配的联系二维码 GET /api/site/contact/qr/${param0}.png */
export async function getPublicContactImage(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicContactImageParams,
  options?: import("@/request").RequestOptions,
) {
  const { sha256: param0, ...queryParams } = params;
  return request<string>(`/api/site/contact/qr/${param0}.png`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 站点信息与实际部署开关 GET /api/site/meta */
export async function getPublicSiteMeta(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PublicSiteMetaView>("/api/site/meta", {
    method: "GET",
    ...(options || {}),
  });
}

/** 当前公开来源的本地回退图标 本地生成,不代理任意URL或调用外部服务。撤回后拒绝读取。 GET /api/site/source-icons/${param0}.svg */
export async function getPublicSourceIcon(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicSourceIconParams,
  options?: import("@/request").RequestOptions,
) {
  const { source_key: param0, ...queryParams } = params;
  return request<string>(`/api/site/source-icons/${param0}.svg`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 当前公开来源的已准入头像缓存 仅当前公开来源且独立MEDIA授权及Evidence缓存有效时读取,GET不采集。 GET /api/site/source-icons/${param0}/${param1} */
export async function getPublicSourceAvatar(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicSourceAvatarParams,
  options?: import("@/request").RequestOptions,
) {
  const { source_key: param0, mode: param1, ...queryParams } = params;
  return request<string>(`/api/site/source-icons/${param0}/${param1}`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 当前许可范围内的公开资料统计 GET /api/site/stats */
export async function getPublicSiteStatistics(
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PublicSiteStatisticsView>("/api/site/stats", {
    method: "GET",
    ...(options || {}),
  });
}
