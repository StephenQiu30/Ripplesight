// @ts-ignore
/* eslint-disable */
import request from "@/request";

/** 受理固定原始内容版本的私有导出 POST /api/content-exports */
export async function createContentExport(
  body: HotKeyAPI.ContentExportInput,
  options?: import("@/request").RequestOptions,
) {
  return request<HotKeyAPI.ExportView>("/api/content-exports", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    data: body,
    ...(options || {}),
  });
}

/** 读取本人内容导出任务状态 GET /api/content-exports/${param0} */
export async function getContentExport(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getContentExportParams,
  options?: import("@/request").RequestOptions,
) {
  const { export_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.ExportView>(`/api/content-exports/${param0}`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 复验全部当前权限后下载本人原始内容文件 GET /api/content-exports/${param0}/download */
export async function downloadContentExport(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.downloadContentExportParams,
  options?: import("@/request").RequestOptions,
) {
  const { export_id: param0, ...queryParams } = params;
  return request<string>(`/api/content-exports/${param0}/download`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 读取本人报告导出任务状态 GET /api/report-exports/${param0} */
export async function getReportExport(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.getReportExportParams,
  options?: import("@/request").RequestOptions,
) {
  const { export_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.ExportView>(`/api/report-exports/${param0}`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 复验全部当前权限后下载本人报告文件 GET /api/report-exports/${param0}/download */
export async function downloadReportExport(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.downloadReportExportParams,
  options?: import("@/request").RequestOptions,
) {
  const { export_id: param0, ...queryParams } = params;
  return request<string>(`/api/report-exports/${param0}/download`, {
    method: "GET",
    params: { ...queryParams },
    ...(options || {}),
  });
}

/** 受理固定报告版本的私有导出 POST /api/reports/${param0}/exports */
export async function createReportExport(
  // 叠加生成的Param类型 (非body参数swagger默认没有生成对象)
  params: HotKeyAPI.createReportExportParams,
  body: HotKeyAPI.ReportExportInput,
  options?: import("@/request").RequestOptions,
) {
  const { report_id: param0, ...queryParams } = params;
  return request<HotKeyAPI.ExportView>(`/api/reports/${param0}/exports`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    params: { ...queryParams },
    data: body,
    ...(options || {}),
  });
}
