"use client";
import * as UI from "@/components/ui/content";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { cancelCollectionJob, retryCollectionJob } from "@/api/caijirenwu";
import {
  createContentExport,
  createReportExport,
  downloadContentExport,
  downloadReportExport,
  getContentExport,
  getReportExport,
} from "@/api/siyoudaochu";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiRequestError } from "@/request";

type ExportTarget =
  | { kind: "report"; reportId: string; reportVersion: number }
  | { kind: "content"; contentVersionIds: string[] };

function errorToast(error: unknown, fallback: string) {
  if (error instanceof ApiRequestError && error.kind === "cancelled") return;
  toast.error(error instanceof ApiRequestError ? error.message : fallback, {
    description:
      error instanceof ApiRequestError && error.requestId
        ? `请求编号: ${error.requestId}`
        : undefined,
  });
}

export function PrivateExport({ target }: { target: ExportTarget }) {
  const key =
    target.kind === "report"
      ? `report:${target.reportId}:${target.reportVersion}`
      : `content:${target.contentVersionIds.join(":")}`;
  return <PrivateExportControl key={key} target={target} />;
}

function PrivateExportControl({ target }: { target: ExportTarget }) {
  const [format, setFormat] = useState<HotKeyAPI.ContentExportInput["format"]>(
    target.kind === "report" ? "markdown" : "csv",
  );
  const [view, setView] = useState<HotKeyAPI.ExportView | null>(null);
  const [busy, setBusy] = useState(false);
  const [pollError, setPollError] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const operation = useRef<string | null>(null);
  const renewedOperation = useRef<string | null>(null);
  const mounted = useRef(true);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      request.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!view || !["pending", "running"].includes(view.status) || pollError)
      return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const read =
        target.kind === "report" ? getReportExport : getContentExport;
      void read({ export_id: view.id }, { signal: controller.signal })
        .then((next) => {
          if (!controller.signal.aborted) setView(next);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          setPollError(true);
          errorToast(error, "导出状态读取失败，可以重新读取。");
        });
    }, 2000);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [view, target.kind, pollError, refresh]);

  async function action(run: (signal: AbortSignal) => Promise<void>) {
    setBusy(true);
    const controller = new AbortController();
    request.current = controller;
    try {
      await run(controller.signal);
    } catch (error) {
      if (!controller.signal.aborted)
        errorToast(error, "导出当前不可用，请复核材料许可后重试。");
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  async function acceptExport(signal: AbortSignal, renew = false) {
    if (renew) {
      renewedOperation.current ??= crypto.randomUUID();
      operation.current = renewedOperation.current;
    } else operation.current ??= crypto.randomUUID();
    const next =
      target.kind === "report"
        ? await createReportExport(
            { report_id: target.reportId },
            {
              operation_id: operation.current,
              report_version: target.reportVersion,
              format,
            },
            { signal },
          )
        : await createContentExport(
            {
              operation_id: operation.current,
              content_version_ids: target.contentVersionIds,
              format,
            },
            { signal },
          );
    if (!signal.aborted) {
      setView(next);
      renewedOperation.current = null;
      setPollError(false);
      toast.success("导出任务已受理，可以在生成完成后下载。");
    }
  }

  const pending = view?.status === "pending" || view?.status === "running";
  const cancelled = view?.failure_code === "export_cancelled";
  const empty = target.kind === "content" && !target.contentVersionIds.length;
  return (
    <UI.Content className="flex flex-wrap items-center gap-3">
      <Select
        value={format}
        disabled={busy || pending}
        onValueChange={(value) => {
          setFormat(value as HotKeyAPI.ContentExportInput["format"]);
          setView(null);
          operation.current = null;
          renewedOperation.current = null;
          setPollError(false);
        }}
      >
        <SelectTrigger aria-label="导出文件格式">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="markdown">Markdown</SelectItem>
          <SelectItem value="pdf">PDF</SelectItem>
          <SelectItem value="csv">CSV</SelectItem>
          <SelectItem value="json">JSON</SelectItem>
        </SelectContent>
      </Select>
      {!view ? (
        <Button
          variant="outline"
          disabled={busy || empty}
          onClick={() => void action((signal) => acceptExport(signal))}
        >
          {busy ? "正在受理…" : "导出私有文件"}
        </Button>
      ) : null}
      {view ? (
        <UI.Text
          as="span"
          className="text-muted-foreground text-sm"
          role="status"
        >
          {cancelled
            ? "导出任务已取消"
            : view.status === "pending"
              ? "导出任务排队中"
              : view.status === "running"
                ? "正在生成文件"
                : view.status === "succeeded"
                  ? `文件已生成 · ${view.artifact_size ?? 0} 字节`
                  : view.status === "blocked"
                    ? "材料权限或固定版本已不可用"
                    : "导出任务失败"}
        </UI.Text>
      ) : null}
      {view?.status === "succeeded" ? (
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            void action(async (signal) => {
              const read =
                target.kind === "report"
                  ? downloadReportExport
                  : downloadContentExport;
              const data: unknown = await read(
                { export_id: view.id },
                { responseType: "blob", signal },
              );
              if (!(data instanceof Blob) || !data.size || data.size > 5242880)
                throw new Error("invalid_export_file");
              const bytes = await data.arrayBuffer();
              const digest = Array.from(
                new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
                (value) => value.toString(16).padStart(2, "0"),
              ).join("");
              if (
                data.size !== view.artifact_size ||
                digest !== view.artifact_sha256
              )
                throw new Error("export_file_changed");
              if (signal.aborted) return;
              const url = URL.createObjectURL(data);
              const link = document.createElement("a");
              link.href = url;
              link.download = `ripplesight-${view.kind}-${view.id}.${view.format === "markdown" ? "md" : view.format}`;
              link.click();
              window.setTimeout(() => URL.revokeObjectURL(url), 1000);
              toast.success("文件已下载。");
            })
          }
        >
          下载文件
        </Button>
      ) : null}
      {pending && view ? (
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() =>
            void action(async (signal) => {
              await cancelCollectionJob({ job_id: view.job_id }, { signal });
              if (!signal.aborted) {
                setPollError(false);
                setRefresh((value) => value + 1);
                toast.success("已请求取消导出任务。");
              }
            })
          }
        >
          取消任务
        </Button>
      ) : null}
      {view?.status === "failed" && !cancelled ? (
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            void action(async (signal) => {
              await retryCollectionJob({ job_id: view.job_id }, { signal });
              if (!signal.aborted) {
                setView({ ...view, status: "pending", failure_code: null });
                setPollError(false);
                toast.success("原导出任务已重新排队。");
              }
            })
          }
        >
          重试原任务
        </Button>
      ) : null}
      {cancelled ? (
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => void action((signal) => acceptExport(signal, true))}
        >
          重新受理
        </Button>
      ) : null}
      {pollError ? (
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => {
            setPollError(false);
            setRefresh((value) => value + 1);
          }}
        >
          重新读取状态
        </Button>
      ) : null}
      {empty ? (
        <UI.Text as="span" className="text-muted-foreground text-sm">
          没有可导出的固定内容版本。
        </UI.Text>
      ) : null}
    </UI.Content>
  );
}
