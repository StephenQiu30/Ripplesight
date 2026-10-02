// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 复核固定正文和当前许可后读取译文 GET /api/translations/${param0} */
export async function getContentTranslation(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getContentTranslationParams,
  options?: import("@/request").RequestOptions,
) {
  const { run_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.TranslationRunView>(`/api/translations/${param0}`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 受理固定全文许可版本的分批翻译 POST /api/translations/contents/${param0} */
export async function requestContentTranslation(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.requestContentTranslationParams,
  body: HotKeyAPI.TranslationRequestInput,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.TranslationRunView>(
    `/api/translations/contents/${param0}`,
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
