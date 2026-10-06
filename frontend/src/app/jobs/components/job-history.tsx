"use client";
import * as UI from "@/components/ui/content";

import { toast } from "sonner";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, RotateCcwIcon } from "lucide-react";

import { listCollectionJobs } from "@/api/caijirenwu";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { PageState } from "@/components/system/page-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";
import { STATUS_LABELS, capabilityLabel, formatTime } from "./job-presenters";

import { JobHealthSummary } from "./job-health-summary";

type HistoryState =
  | { status: "loading" }
  | {
      status: "ready";
      items: HotKeyAPI.JobHistoryItemView[];
      nextCursor: string | null;
    }
  | { status: "error"; message: string; requestId?: string };

function toErrorState(
  error: unknown,
): Extract<HistoryState, { status: "error" }> {
  return error instanceof ApiRequestError
    ? { status: "error", message: error.message, requestId: error.requestId }
    : { status: "error", message: "任务记录加载失败，请稍后重试。" };
}

function jobKindLabel(kind: string): string {
  switch (kind) {
    case "monitor.collect":
      return "监控采集";
    case "webpage.collect":
      return "网页采集";
    case "source.hotlist":
      return "热榜采集";
    default:
      return kind;
  }
}

function statusVariant(
  status: HotKeyAPI.JobControlStatus,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "failed") {
    return "destructive";
  }
  if (status === "succeeded" || status === "partially_succeeded") {
    return "secondary";
  }
  return "outline";
}

export function JobHistoryCard({ job }: { job: HotKeyAPI.JobHistoryItemView }) {
  return (
    <UI.Content
      as="article"
      className="flex flex-col gap-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-8"
    >
      <UI.Content className="min-w-0">
        <UI.Content className="flex flex-wrap items-center gap-2">
          <UI.Heading level={2} className="text-lg font-medium">
            {jobKindLabel(job.kind)}
          </UI.Heading>
          <Badge variant={statusVariant(job.status)}>
            {STATUS_LABELS[job.status]}
          </Badge>
          {job.source_key ? (
            <UI.Text as="span" className="text-muted-foreground text-xs">
              {job.source_key}
              {job.source_capability
                ? ` · ${capabilityLabel(job.source_capability)}`
                : ""}
            </UI.Text>
          ) : null}
        </UI.Content>
        <UI.Text className="text-muted-foreground mt-3 text-sm">
          创建于 {formatTime(job.created_at)}
        </UI.Text>
        <UI.Text className="text-muted-foreground mt-1 text-xs">
          请求 {job.requests_sent} 次 · 已保存 {job.items_saved} 条
          {job.next_run_at ? ` · 下次运行 ${formatTime(job.next_run_at)}` : ""}
        </UI.Text>
      </UI.Content>
      <Button asChild variant="ghost" size="sm" className="self-start">
        <Link href={`/jobs/${job.id}`}>
          查看详情
          <ArrowRightIcon data-icon="inline-end" />
        </Link>
      </Button>
    </UI.Content>
  );
}

type JobHistoryContentProps = {
  items: HotKeyAPI.JobHistoryItemView[];
  nextCursor: string | null;
  isLoadingMore: boolean;
  onLoadMore: () => void;
};

export function JobHistoryContent({
  items,
  nextCursor,
  isLoadingMore,
  onLoadMore,
}: JobHistoryContentProps) {
  return (
    <>
      {items.length === 0 ? (
        <Empty className="mt-12">
          <EmptyHeader>
            <EmptyTitle>尚无任务记录</EmptyTitle>
            <EmptyDescription>
              提交采集任务后，状态和进度会显示在这里。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <UI.Content className="mt-8 flex flex-col gap-6">
          {items.map((job) => (
            <JobHistoryCard key={job.id} job={job} />
          ))}
        </UI.Content>
      )}

      {nextCursor ? (
        <UI.Content className="mt-8 flex justify-center">
          <Button
            type="button"
            variant="secondary"
            onClick={onLoadMore}
            disabled={isLoadingMore}
          >
            {isLoadingMore ? "正在加载" : "加载更多"}
          </Button>
        </UI.Content>
      ) : null}
    </>
  );
}

export function JobHistory() {
  const [state, setState] = useState<HistoryState>({ status: "loading" });
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const request = useRef<AbortController | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const loadingMoreRef = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    request.current = controller;
    void listCollectionJobs({ limit: 20 }, { signal: controller.signal })
      .then((page) => {
        if (!controller.signal.aborted) {
          setState({
            status: "ready",
            items: page.items,
            nextCursor: page.next_cursor,
          });
        }
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (controller.signal.aborted) {
          return;
        }

        const failure = toErrorState(error);
        toast.error(failure.message, {
          description: failure.requestId
            ? `请求编号：${failure.requestId}`
            : undefined,
        });
        setState(failure);
      });
    return () => {
      controller.abort();
    };
  }, [reloadToken]);

  function reload() {
    request.current?.abort();
    loadingMoreRef.current = false;
    setIsLoadingMore(false);
    setState({ status: "loading" });
    setReloadToken((value) => value + 1);
  }

  async function loadMore() {
    if (
      state.status !== "ready" ||
      state.nextCursor === null ||
      loadingMoreRef.current
    ) {
      return;
    }
    const controller = request.current;
    if (!controller || controller.signal.aborted) return;
    loadingMoreRef.current = true;
    setIsLoadingMore(true);
    try {
      const page = await listCollectionJobs(
        {
          cursor: state.nextCursor,
          limit: 20,
        },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setState({
        status: "ready",
        items: [...state.items, ...page.items],
        nextCursor: page.next_cursor,
      });
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (controller.signal.aborted) return;
      toast.error(
        error instanceof ApiRequestError
          ? error.message
          : "后续任务加载失败，请重试。",
      );
    } finally {
      if (!controller.signal.aborted) {
        loadingMoreRef.current = false;
        setIsLoadingMore(false);
      }
    }
  }

  if (state.status === "loading") {
    return (
      <>
        <UI.Heading level={1} className="sr-only">
          正在读取任务
        </UI.Heading>
        <PageState
          state="loading"
          eyebrow="任务记录"
          title="正在读取任务"
          description="正在读取已保存的任务记录。"
        />
      </>
    );
  }

  if (state.status === "error") {
    return (
      <PageState
        state="error"
        eyebrow="加载失败"
        title="暂时无法读取任务记录"
        description="请重新加载任务记录。"
        action={
          <Button onClick={() => void reload()}>
            <RotateCcwIcon data-icon="inline-start" />
            重新加载
          </Button>
        }
      />
    );
  }

  return (
    <UI.Content>
      <UI.Heading
        level={1}
        className="mt-3 text-3xl font-normal tracking-tight sm:text-4xl"
      >
        任务记录
      </UI.Heading>
      <UI.Text className="text-muted-foreground mt-4 max-w-2xl leading-7">
        查看任务状态与已持久保存的进度。
      </UI.Text>

      <JobHealthSummary />

      <JobHistoryContent
        items={state.items}
        nextCursor={state.nextCursor}
        isLoadingMore={isLoadingMore}
        onLoadMore={() => void loadMore()}
      />
    </UI.Content>
  );
}
