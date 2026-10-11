"use client";

import { useEffect, useState } from "react";

import { getCollectionJob } from "@/api/caijirenwu";
import { CollectionIdentityCounts } from "@/components/collection/identity-counts";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import * as UI from "@/components/ui/content";
import { Spinner } from "@/components/ui/spinner";
import { ApiRequestError } from "@/request";

type Receipt = Pick<
  HotKeyAPI.JobStatusView,
  "id" | "kind" | "collection_counts"
>;
type ReadState = {
  status: "idle" | "ready" | "error";
  requestKey?: string;
  receipt: Receipt | null;
  failure?: "unavailable" | "forbidden" | "read";
};

/** Read the existing whole-job receipt only while its list disclosure is open. */
export function JobCollectionCounts({
  jobId,
  kind,
}: {
  jobId: string;
  kind: "keyword.search" | "source.comments";
}) {
  const [open, setOpen] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<ReadState>({
    status: "idle",
    receipt: null,
  });
  const requestKey = `${jobId}:${kind}:${refresh}`;
  const status = state.requestKey === requestKey ? state.status : "loading";

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void getCollectionJob({ job_id: jobId }, { signal: controller.signal })
      .then((receipt) => {
        if (controller.signal.aborted) return;
        if (receipt.id !== jobId || receipt.kind !== kind) {
          setState({
            status: "error",
            requestKey,
            receipt: null,
            failure: "unavailable",
          });
          return;
        }
        setState({ status: "ready", requestKey, receipt });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const status = error instanceof ApiRequestError ? error.status : null;
        const forbidden = status === 401 || status === 403;
        const unavailable = status === 404;
        setState((previous) => ({
          status: "error",
          requestKey,
          receipt: forbidden || unavailable ? null : previous.receipt,
          failure: forbidden
            ? "forbidden"
            : unavailable
              ? "unavailable"
              : "read",
        }));
      });
    return () => controller.abort();
  }, [jobId, kind, open, requestKey]);

  const receipt =
    state.receipt?.id === jobId && state.receipt.kind === kind
      ? state.receipt
      : null;
  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => {
        if (next) setRefresh((value) => value + 1);
        setOpen(next);
      }}
    >
      <CollapsibleTrigger asChild>
        <Button variant="outline" size="sm">
          {open ? "收起累计计量" : "查看累计计量"}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        {open ? (
          <UI.Content
            as="section"
            aria-label="任务累计计量"
            className="mt-4 flex min-w-0 flex-col gap-4"
          >
            <UI.Content className="flex flex-wrap items-center justify-between gap-3">
              <UI.Heading level={3}>任务累计计量</UI.Heading>
              <Button
                size="sm"
                variant="outline"
                disabled={status === "loading"}
                onClick={() => setRefresh((value) => value + 1)}
              >
                {status === "error" ? "重试计量" : "刷新计量"}
              </Button>
            </UI.Content>
            <UI.Text size="sm" tone="muted">
              按整个任务 ID 累计，包含全部重试，不是当前执行轮次的新增量。
              列表进度与此计量分别读取，不跨快照计算比例。
            </UI.Text>
            {status === "loading" ? (
              <UI.Content role="status" className="flex items-center gap-2">
                <Spinner />
                <UI.Text size="sm" tone="muted">
                  {receipt
                    ? "正在刷新，暂时显示上次计量。"
                    : "正在读取累计计量。"}
                </UI.Text>
              </UI.Content>
            ) : null}
            {status === "error" ? (
              <Alert variant="destructive">
                <AlertTitle>
                  {receipt
                    ? "计量刷新失败，已显示内容可能过期"
                    : state.failure === "forbidden"
                      ? "暂时无法访问任务计量"
                      : state.failure === "unavailable"
                        ? "任务计量不存在或暂不可读"
                        : "无法读取累计计量"}
                </AlertTitle>
                <AlertDescription>
                  {state.failure === "forbidden"
                    ? "请使用有权限的账号重新核对。"
                    : "可重试读取，失败不表示采集结果为零。"}
                </AlertDescription>
              </Alert>
            ) : null}
            {receipt ? (
              <CollectionIdentityCounts row={receipt.collection_counts ?? {}} />
            ) : null}
          </UI.Content>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}
