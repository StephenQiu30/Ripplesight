// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 显式受理固定正文媒体镜像 只接受当前已获准精选全文的固定候选;不允许任意URL,同版本/许可修订复用已有Job。 POST /api/publication/items/${param0}/media */
export async function requestPublicationMediaMirror(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.requestPublicationMediaMirrorParams,
  body: HotKeyAPI.MediaMirrorInput,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.MediaMirrorRunView>(
    `/api/publication/items/${param0}/media`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      params: { ...queryParams },
      data: body,
      ...(options || {}),
    },
  );
}

/** 读取明确获准再分发的固定媒体字节 GET /api/publication/media/${param0}/${param1} */
export async function getPublicationMedia(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationMediaParams,
  options?: import("@/request").RequestOptions,
) {
  const { file_id: param0, mode: param1, ...queryParams } = params;
  return request<any>(`/api/publication/media/${param0}/${param1}`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 读取站内许可的固定媒体字节 GET /api/publication/media/${param0}/${param1}/site */
export async function getSitePublicationMedia(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getSitePublicationMediaParams,
  options?: import("@/request").RequestOptions,
) {
  const { file_id: param0, mode: param1, ...queryParams } = params;
  return request<any>(`/api/publication/media/${param0}/${param1}/site`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 读取媒体镜像任务状态 GET /api/publication/media/runs/${param0} */
export async function getPublicationMediaMirrorRun(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getPublicationMediaMirrorRunParams,
  options?: import("@/request").RequestOptions,
) {
  const { run_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.MediaMirrorRunView>(
    `/api/publication/media/runs/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}
