"use client";

import { useEffect, useState } from "react";

import { getCollectionJob } from "@/api/caijirenwu";
import { JobExecutionCounts } from "@/components/collection/execution-counts";
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
  | "id"
  | "kind"
  | "collection_counts"
  | "collection_executions"
  | "collection_executions_has_more"
>;
type ReadState = {
  status: "idle" | "ready" | "error";
  requestKey?: string;
  receipt: Receipt | null;
  failure?: "unavailable" | "forbidden" | "read";
};

/** Read a task receipt only after explicit expansion of a proven task reference. */
export function JobCollectionCounts({
  jobId,
  kind,
  scope = "job",
}: {
  jobId: string;
  kind?: "keyword.search" | "source.comments";
  scope?: "job" | "execution";
}) {
  const [open, setOpen] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [state, setState] = useState<ReadState>({
    status: "idle",
    receipt: null,
  });
  const requestKey = `${jobId}:${kind ?? "unknown"}:${scope}:${refresh}`;
  const status = state.requestKey === requestKey ? state.status : "loading";

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    void getCollectionJob({ job_id: jobId }, { signal: controller.signal })
      .then((receipt) => {
        if (controller.signal.aborted) return;
        if (
          receipt.id !== jobId ||
          (kind !== undefined && receipt.kind !== kind)
        ) {
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
    state.receipt?.id === jobId &&
    (kind === undefined || state.receipt.kind === kind)
      ? state.receipt
      : null;
  const supported =
    receipt?.kind === "keyword.search" || receipt?.kind === "source.comments";
  const label = scope === "job" ? "累计与逐轮计量" : "逐轮摘要";
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
          {open ? `收起${label}` : `查看${label}`}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        {open ? (
          <UI.Content
            as="section"
            aria-label={scope === "job" ? "任务计量" : "关联任务逐轮摘要"}
            className="mt-4 flex min-w-0 flex-col gap-4"
          >
            <UI.Content className="flex flex-wrap items-center justify-between gap-3">
              <UI.Heading level={3}>
                {scope === "job" ? "任务累计与逐轮计量" : "关联任务逐轮摘要"}
              </UI.Heading>
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
              {scope === "job"
                ? "累计按整个任务 ID 统计，包含全部重试，不是当前执行轮次的新增量。"
                : "以下是关联任务的执行轮计量，不是当前覆盖窗口、主题整轮或单份材料的独立增量。"}
              列表、累计与单轮各有读取范围，不跨快照相减、加总或计算比例。
            </UI.Text>
            <UI.Text size="sm" tone="muted" className="wrap-anywhere">
              关联任务：{jobId}
            </UI.Text>
            {status === "loading" ? (
              <UI.Content role="status" className="flex items-center gap-2">
                <Spinner />
                <UI.Text size="sm" tone="muted">
                  {receipt
                    ? "正在刷新，暂时显示上次计量。"
                    : "正在读取任务计量。"}
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
                        : "无法读取任务计量"}
                </AlertTitle>
                <AlertDescription>
                  {state.failure === "forbidden"
                    ? "请使用有权限的账号重新核对。"
                    : "可重试读取，失败不表示采集结果为零。"}
                </AlertDescription>
              </Alert>
            ) : null}
            {receipt && !supported ? (
              <UI.Text tone="muted">
                该任务类型不提供关键词/评论单轮计量，不推断为零轮。
              </UI.Text>
            ) : null}
            {receipt && supported ? (
              <>
                {scope === "job" ? (
                  <CollectionIdentityCounts
                    row={receipt.collection_counts ?? {}}
                  />
                ) : null}
                <JobExecutionCounts
                  key={`${receipt.id}:${receipt.kind}`}
                  job={receipt}
                  headingLevel={4}
                />
              </>
            ) : null}
          </UI.Content>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}
