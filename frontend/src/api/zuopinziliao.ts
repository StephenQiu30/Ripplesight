// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 列出作品资料 按当前 owner 列出具有可读观察的作品及当前来源状态; 读取不会触发来源请求。 GET /api/contents */
export async function listContentRecords(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listContentRecordsParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.PageViewContentRecordSummaryView_>("/api/contents", {
    method: "GET",
    params: {
      // limit has a default value: 20
      limit: "20",
      ...params,
    },
    ...(options || {}),
  });
}

/** 读取作品资料 读取当前 owner 的作品身份、最新可读观察、版本/可见性历史与发现依据; 不隐式刷新。 GET /api/contents/${param0} */
export async function getContentRecord(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getContentRecordParams,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.ContentRecordDetailView>(`/api/contents/${param0}`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 复采作品评论 对当前 owner 已入库且仍属于活跃主题的 HN 帖子受理一次有界评论复采。 POST /api/contents/${param0}/comment-runs */
export async function runContentComments(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.runContentCommentsParams,
  body: HotKeyAPI.CommentManualRunInput,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.JobAcceptedView>(
    `/api/contents/${param0}/comment-runs`,
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

/** 分页读取作品评论 按线程根、指定根的各层回复或指定直接父节点读取本地可读评论。读取不会触发来源请求。 GET /api/contents/${param0}/comments */
export async function listContentComments(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listContentCommentsParams,
  options?: import("@/request").RequestOptions,
) {
  const { content_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.PageViewContentCommentView_>(
    `/api/contents/${param0}/comments`,
    {
      method: "GET",
      params: {
        // limit has a default value: 20
        limit: "20",
        ...queryParams,
      },
      ...(options || {}),
    },
  );
}
