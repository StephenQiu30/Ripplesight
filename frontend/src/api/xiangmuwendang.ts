// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** Catalog GET /api/workspace/documents */
export async function listWorkspaceDocuments(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.listWorkspaceDocumentsParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.WorkspaceCatalogView>("/api/workspace/documents", {
    method: "GET",
    params: {
      ...params,
    },
    ...(options || {}),
  });
}

/** Attachment GET /api/workspace/documents/attachment */
export async function getWorkspaceDocumentAttachment(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getWorkspaceDocumentAttachmentParams,
  options?: import("@/request").RequestOptions,
) {
  return request<any>("/api/workspace/documents/attachment", {
    method: "GET",
    params: {
      ...params,
    },
    ...(options || {}),
  });
}

/** Document GET /api/workspace/documents/document */
export async function getWorkspaceDocument(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getWorkspaceDocumentParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.WorkspaceDocumentView>(
    "/api/workspace/documents/document",
    {
      method: "GET",
      params: {
        ...params,
      },
      ...(options || {}),
    },
  );
}

/** Draft GET /api/workspace/documents/draft */
export async function getWorkspaceDocumentDraft(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getWorkspaceDocumentDraftParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.WorkspaceDraftView>(
    "/api/workspace/documents/draft",
    {
      method: "GET",
      params: {
        ...params,
      },
      ...(options || {}),
    },
  );
}

/** Save PUT /api/workspace/documents/draft */
export async function saveWorkspaceDocumentDraft(
  body: HotKeyAPI.WorkspaceSaveInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.WorkspaceDraftView>(
    "/api/workspace/documents/draft",
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

/** History GET /api/workspace/documents/history */
export async function getWorkspaceDocumentHistory(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getWorkspaceDocumentHistoryParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.WorkspaceHistoryView>(
    "/api/workspace/documents/history",
    {
      method: "GET",
      params: {
        ...params,
      },
      ...(options || {}),
    },
  );
}

/** Operation GET /api/workspace/documents/operations/${param0} */
export async function getWorkspaceDocumentOperation(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getWorkspaceDocumentOperationParams,
  options?: import("@/request").RequestOptions,
) {
  const { operation_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.WorkspaceOperationView>(
    `/api/workspace/documents/operations/${param0}`,
    {
      method: "GET",
      params: { ...queryParams },
      ...(options || {}),
    },
  );
}

/** Publish POST /api/workspace/documents/publish */
export async function publishWorkspaceDocument(
  body: HotKeyAPI.WorkspacePublishInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.WorkspaceOperationView>(
    "/api/workspace/documents/publish",
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

/** Raw GET /api/workspace/documents/raw */
export async function getWorkspaceDocumentRaw(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getWorkspaceDocumentRawParams,
  options?: import("@/request").RequestOptions,
) {
  return request<any>("/api/workspace/documents/raw", {
    method: "GET",
    params: {
      ...params,
    },
    ...(options || {}),
  });
}

/** Search GET /api/workspace/documents/search */
export async function searchWorkspaceDocuments(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.searchWorkspaceDocumentsParams,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.WorkspaceSearchView>(
    "/api/workspace/documents/search",
    {
      method: "GET",
      params: {
        ...params,
      },
      ...(options || {}),
    },
  );
}
