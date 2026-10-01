"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, RotateCcwIcon } from "lucide-react";

import { listCollectionJobs } from "@/api/caijirenwu";
import { WorkspaceHeader } from "@/components/navigation/workspace-header";
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

import { JobHealthSummary } from "./job-health-summary";

type HistoryState =
  | { status: "loading" }
  | {
      status: "ready";
      items: HotKeyAPI.JobHistoryItemView[];
      nextCursor: string | null;
    }
  | { status: "error"; message: string; requestId?: string };

const STATUS_LABELS: Record<HotKeyAPI.JobControlStatus, string> = {
  queued: "排队中",
  running: "执行中",
  cancelling: "取消中",
  succeeded: "已完成",
  partially_succeeded: "部分完成",
  failed: "失败",
  cancelled: "已取消",
};

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

function capabilityLabel(capability: HotKeyAPI.SourceCapability): string {
  switch (capability) {
    case "search":
      return "检索";
    case "author_posts":
      return "作者作品";
    case "comments":
      return "评论";
    case "replies":
      return "回复";
    case "page_content":
      return "页面正文";
    case "hotlist":
      return "热榜";
  }
}

function formatTime(value: string | null): string {
  if (value === null) {
    return "—";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
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
    <article className="flex flex-col gap-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-8">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-medium">{jobKindLabel(job.kind)}</h2>
          <Badge variant={statusVariant(job.status)}>
            {STATUS_LABELS[job.status]}
          </Badge>
          {job.source_key ? (
            <span className="text-muted-foreground text-xs">
              {job.source_key}
              {job.source_capability
                ? ` · ${capabilityLabel(job.source_capability)}`
                : ""}
            </span>
          ) : null}
        </div>
        <p className="text-muted-foreground mt-3 text-sm">
          创建于 {formatTime(job.created_at)}
        </p>
        <p className="text-muted-foreground mt-1 text-xs">
          请求 {job.requests_sent} 次 · 已保存 {job.items_saved} 条
          {job.next_run_at ? ` · 下次运行 ${formatTime(job.next_run_at)}` : ""}
        </p>
      </div>
      <Button asChild variant="ghost" size="sm" className="self-start">
        <Link href={`/jobs/${job.id}`}>
          查看详情
          <ArrowRightIcon data-icon="inline-end" />
        </Link>
      </Button>
    </article>
  );
}

type JobHistoryContentProps = {
  items: HotKeyAPI.JobHistoryItemView[];
  nextCursor: string | null;
  isLoadingMore: boolean;
  loadMoreError: string | null;
  onLoadMore: () => void;
};

export function JobHistoryContent({
  items,
  nextCursor,
  isLoadingMore,
  loadMoreError,
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
        <div className="mt-8 flex flex-col gap-6">
          {items.map((job) => (
            <JobHistoryCard key={job.id} job={job} />
          ))}
        </div>
      )}

      {nextCursor ? (
        <div className="mt-8 flex justify-center">
          <Button
            type="button"
            variant="secondary"
            onClick={onLoadMore}
            disabled={isLoadingMore}
          >
            {isLoadingMore ? "正在加载" : "加载更多"}
          </Button>
        </div>
      ) : null}
      {loadMoreError ? (
        <p role="alert" className="text-destructive mt-3 text-center text-sm">
          {loadMoreError}
        </p>
      ) : null}
    </>
  );
}

export function JobHistory() {
  const [state, setState] = useState<HistoryState>({ status: "loading" });
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
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
        if (controller.signal.aborted) {
          return;
        }

        setState(toErrorState(error));
      });
    return () => {
      controller.abort();
    };
  }, [reloadToken]);

  function reload() {
    request.current?.abort();
    loadingMoreRef.current = false;
    setIsLoadingMore(false);
    setLoadMoreError(null);
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
    setLoadMoreError(null);
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
      if (controller.signal.aborted) return;
      setLoadMoreError(
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
      <PageState
        navigation={<WorkspaceHeader current="jobs" />}
        eyebrow="任务记录"
        title="正在读取任务"
        description="正在读取已保存的任务记录。"
      />
    );
  }

  if (state.status === "error") {
    return (
      <PageState
        navigation={<WorkspaceHeader current="jobs" />}
        eyebrow="加载失败"
        title="暂时无法读取任务记录"
        description={
          state.requestId
            ? `${state.message} 请求编号：${state.requestId}`
            : state.message
        }
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
    <div className="bg-background min-h-screen">
      <WorkspaceHeader current="jobs" />

      <main className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
        <h1 className="mt-3 text-3xl font-normal tracking-tight sm:text-4xl">
          任务记录
        </h1>
        <p className="text-muted-foreground mt-4 max-w-2xl leading-7">
          查看任务状态与已持久保存的进度。
        </p>

        <JobHealthSummary />

        <JobHistoryContent
          items={state.items}
          nextCursor={state.nextCursor}
          isLoadingMore={isLoadingMore}
          loadMoreError={loadMoreError}
          onLoadMore={() => void loadMore()}
        />
      </main>
    </div>
  );
}
