"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowDownIcon,
  ArrowRightIcon,
  ArrowUpIcon,
  ExternalLinkIcon,
  RotateCcwIcon,
} from "lucide-react";

import {
  getHistoricalHotlistSnapshot,
  listHotlistSnapshots,
  listHotlistSources,
} from "@/api/rebang";

import { WorkspaceHeader } from "@/components/navigation/workspace-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageState } from "@/components/system/page-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/request";

import { formatHotlistTime, SnapshotSelector } from "./snapshot-selector";

const SOURCES = [
  { key: "hotlist_36kr", label: "36Kr" },
  { key: "hotlist_baidu", label: "百度" },
  { key: "hotlist_bilibili", label: "B 站" },
  { key: "hotlist_thepaper", label: "澎湃" },
  { key: "hotlist_weibo", label: "微博" },
  { key: "hotlist_zhihu", label: "知乎" },
] as const;

type SourcesState =
  | { status: "loading" }
  | { status: "ready"; items: HotKeyAPI.HotlistSourceView[] }
  | { status: "error"; message: string; requestId?: string };

type HistoryState =
  | { status: "loading"; sourceKey: string }
  | {
      status: "ready";
      sourceKey: string;
      items: HotKeyAPI.HotlistSnapshotSummaryView[];
      nextCursor: string | null;
    }
  | { status: "error"; sourceKey: string; message: string; requestId?: string };

type DetailState =
  | { status: "loading"; snapshotId: string }
  | {
      status: "ready";
      snapshotId: string;
      value: HotKeyAPI.HotlistSnapshotView;
    }
  | {
      status: "error";
      snapshotId: string;
      message: string;
      requestId?: string;
      forbidden: boolean;
    };

function safeExternalHref(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:"
      ? url.href
      : null;
  } catch {
    return null;
  }
}

function readError(error: unknown, fallback: string) {
  return error instanceof ApiRequestError
    ? { message: error.message, requestId: error.requestId }
    : { message: fallback };
}

export async function resolveSnapshotRequest(
  sourceKey: string,
  snapshotId: string,
  signal: AbortSignal,
): Promise<HotKeyAPI.HotlistSnapshotView | null> {
  const result = await getHistoricalHotlistSnapshot(
    { source_key: sourceKey, snapshot_id: snapshotId, limit: 20 },
    { signal },
  );
  return signal.aborted ? null : result;
}

function rankLabel(entry: HotKeyAPI.HotlistEntryView): string {
  switch (entry.rank_change) {
    case "up":
      return `上升 ${entry.rank_delta ?? 0}`;
    case "down":
      return `下降 ${Math.abs(entry.rank_delta ?? 0)}`;
    case "same":
      return "持平";
    case "new":
      return "新上榜";
  }
}

function InlineState({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <Empty className="mt-12">
      <EmptyHeader>
        <p className="text-muted-foreground text-sm">{eyebrow}</p>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
      {action}
    </Empty>
  );
}

export function SnapshotDetail({
  snapshot,
}: {
  snapshot: HotKeyAPI.HotlistSnapshotView;
}) {
  return (
    <section aria-label="热榜快照" className="mt-10">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h2 className="text-xl font-medium tracking-tight">
          {formatHotlistTime(snapshot.observed_at)}
        </h2>
        <Badge variant="secondary">{snapshot.entry_count} 条</Badge>
        {(snapshot.gap_count ?? 0) > 0 ? (
          <Alert className="mt-4">
            <AlertTitle>快照有缺口</AlertTitle>
            <AlertDescription>
              此前 {snapshot.gap_count} 个采集窗口无快照
            </AlertDescription>
          </Alert>
        ) : null}
      </div>
      <p className="text-muted-foreground mt-3 text-sm leading-6">
        {snapshot.previous_snapshot_id
          ? "排名与同来源前一成功快照比较。"
          : "这是该来源的首个成功快照，所有榜位均为新上榜。"}
      </p>
      {snapshot.previous_snapshot_id ? (
        <Link
          className="text-foreground mt-2 inline-flex items-center gap-1 text-sm underline underline-offset-4"
          href={`/hotlists?source=${encodeURIComponent(snapshot.source_key)}&snapshot=${encodeURIComponent(snapshot.previous_snapshot_id)}`}
        >
          查看前一快照 <ArrowRightIcon className="size-4" aria-hidden="true" />
        </Link>
      ) : null}
      {snapshot.entry_count === 0 ? (
        <Empty className="mt-8">
          <EmptyHeader>
            <EmptyTitle>本次观察到空榜</EmptyTitle>
            <EmptyDescription>这是一条成功的零条目快照。</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <ol className="mt-10 flex flex-col gap-8">
          {snapshot.items.map((entry) => {
            const originalHref = safeExternalHref(entry.url);
            return (
              <li key={entry.rank} className="py-4">
                <div className="flex items-start gap-4">
                  <span className="text-muted-foreground w-8 shrink-0 text-xl tabular-nums">
                    {entry.rank}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge
                        variant={
                          entry.rank_change === "up" ? "secondary" : "outline"
                        }
                      >
                        {entry.rank_change === "up" ? (
                          <ArrowUpIcon aria-hidden="true" />
                        ) : null}
                        {entry.rank_change === "down" ? (
                          <ArrowDownIcon aria-hidden="true" />
                        ) : null}
                        {rankLabel(entry)}
                      </Badge>
                      {entry.matched ? (
                        <Badge variant="secondary">命中主题</Badge>
                      ) : null}
                    </div>
                    <h3 className="mt-3 text-base leading-7 font-medium break-words">
                      {entry.title}
                    </h3>
                    {entry.summary ? (
                      <p className="text-muted-foreground mt-2 line-clamp-3 text-sm leading-6 break-words">
                        {entry.summary}
                      </p>
                    ) : null}
                    {entry.matched_topic_names.length > 0 ? (
                      <p className="text-muted-foreground mt-3 text-xs">
                        主题：{entry.matched_topic_names.join("、")}
                      </p>
                    ) : null}
                    <div className="mt-4 flex flex-wrap gap-4 text-sm">
                      {entry.content_id ? (
                        <Link
                          className="text-foreground inline-flex items-center gap-1 underline underline-offset-4"
                          href={`/content/${entry.content_id}`}
                        >
                          查看作品资料{" "}
                          <ArrowRightIcon
                            className="size-4"
                            aria-hidden="true"
                          />
                        </Link>
                      ) : null}
                      {originalHref ? (
                        <a
                          className="text-muted-foreground inline-flex items-center gap-1 underline underline-offset-4"
                          href={originalHref}
                          target="_blank"
                          rel="noreferrer"
                        >
                          打开原文{" "}
                          <ExternalLinkIcon
                            className="size-4"
                            aria-hidden="true"
                          />
                        </a>
                      ) : null}
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

export function HotlistWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedSource = searchParams.get("source");
  const requestedSnapshot = searchParams.get("snapshot");
  const [sources, setSources] = useState<SourcesState>({ status: "loading" });
  const [history, setHistory] = useState<HistoryState | null>(null);
  const [detail, setDetail] = useState<DetailState | null>(null);
  const [loadingHistoryMore, setLoadingHistoryMore] = useState(false);
  const [loadingEntriesMore, setLoadingEntriesMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [detailRefresh, setDetailRefresh] = useState(0);
  const historyRequest = useRef<AbortController | null>(null);
  const detailRequest = useRef<AbortController | null>(null);
  const historyMorePending = useRef(false);
  const entriesMorePending = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    void listHotlistSources({ signal: controller.signal })
      .then((page) => {
        if (!controller.signal.aborted)
          setSources({ status: "ready", items: page.items });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;

        setSources({
          status: "error",
          ...readError(error, "热榜来源加载失败，请重试。"),
        });
      });
    return () => {
      controller.abort();
    };
  }, []);

  const activeSource =
    requestedSource ??
    (sources.status === "ready" ? sources.items[0]?.source_key : null);
  const applied =
    sources.status === "ready" &&
    sources.items.some((item) => item.source_key === activeSource);

  useEffect(() => {
    if (!activeSource || !applied) return;
    const controller = new AbortController();
    historyRequest.current = controller;
    historyMorePending.current = false;
    void listHotlistSnapshots(
      { source_key: activeSource, limit: 20 },
      { signal: controller.signal },
    )
      .then((page) => {
        if (controller.signal.aborted) return;
        setLoadingHistoryMore(false);
        setMoreError(null);
        setHistory({
          status: "ready",
          sourceKey: activeSource,
          items: page.items,
          nextCursor: page.next_cursor,
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;

        setHistory({
          status: "error",
          sourceKey: activeSource,
          ...readError(error, "热榜历史加载失败，请重试。"),
        });
      });
    return () => controller.abort();
  }, [activeSource, applied, historyRefresh]);

  const selectedSnapshot =
    history?.status === "ready" && history.sourceKey === activeSource
      ? (requestedSnapshot ?? history.items[0]?.snapshot_id)
      : null;

  useEffect(() => {
    if (!activeSource || !selectedSnapshot) return;
    const controller = new AbortController();
    detailRequest.current = controller;
    entriesMorePending.current = false;
    void resolveSnapshotRequest(
      activeSource,
      selectedSnapshot,
      controller.signal,
    )
      .then((snapshot) => {
        if (!snapshot || controller.signal.aborted) return;
        setLoadingEntriesMore(false);
        setMoreError(null);
        setDetail({
          status: "ready",
          snapshotId: selectedSnapshot,
          value: snapshot,
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;

        setDetail({
          status: "error",
          snapshotId: selectedSnapshot,
          forbidden:
            error instanceof ApiRequestError &&
            (error.status === 403 || error.status === 404),
          ...readError(error, "快照加载失败，请重试。"),
        });
      });
    return () => controller.abort();
  }, [activeSource, selectedSnapshot, detailRefresh]);

  function selectSource(sourceKey: string) {
    historyRequest.current?.abort();
    detailRequest.current?.abort();
    historyMorePending.current = false;
    entriesMorePending.current = false;
    setLoadingHistoryMore(false);
    setLoadingEntriesMore(false);
    setMoreError(null);
    router.replace(`/hotlists?source=${encodeURIComponent(sourceKey)}`);
  }

  function selectSnapshot(snapshotId: string) {
    if (!activeSource) return;
    detailRequest.current?.abort();
    entriesMorePending.current = false;
    setLoadingEntriesMore(false);
    setMoreError(null);
    router.replace(
      `/hotlists?source=${encodeURIComponent(activeSource)}&snapshot=${encodeURIComponent(snapshotId)}`,
    );
  }

  async function loadHistoryMore() {
    if (
      !activeSource ||
      history?.status !== "ready" ||
      history.sourceKey !== activeSource ||
      !history.nextCursor ||
      historyMorePending.current
    )
      return;
    const controller = historyRequest.current;
    if (!controller || controller.signal.aborted) return;
    historyMorePending.current = true;
    setLoadingHistoryMore(true);
    setMoreError(null);
    try {
      const page = await listHotlistSnapshots(
        {
          source_key: activeSource,
          cursor: history.nextCursor,
          limit: 20,
        },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setHistory((current) =>
        current?.status === "ready" && current.sourceKey === activeSource
          ? {
              ...current,
              items: [...current.items, ...page.items],
              nextCursor: page.next_cursor,
            }
          : current,
      );
    } catch (error) {
      if (controller.signal.aborted) return;
      setMoreError(readError(error, "后续历史加载失败，请重试。").message);
    } finally {
      if (!controller.signal.aborted) {
        historyMorePending.current = false;
        setLoadingHistoryMore(false);
      }
    }
  }

  async function loadEntriesMore() {
    if (
      !activeSource ||
      !selectedSnapshot ||
      detail?.status !== "ready" ||
      detail.snapshotId !== selectedSnapshot ||
      !detail.value.next_cursor ||
      entriesMorePending.current
    )
      return;
    const controller = detailRequest.current;
    if (!controller || controller.signal.aborted) return;
    entriesMorePending.current = true;
    setLoadingEntriesMore(true);
    setMoreError(null);
    try {
      const page = await getHistoricalHotlistSnapshot(
        {
          source_key: activeSource,
          snapshot_id: selectedSnapshot,
          cursor: detail.value.next_cursor,
          limit: 20,
        },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setDetail((current) =>
        current?.status === "ready" && current.snapshotId === selectedSnapshot
          ? {
              ...current,
              value: {
                ...current.value,
                items: [...current.value.items, ...page.items],
                next_cursor: page.next_cursor,
              },
            }
          : current,
      );
    } catch (error) {
      if (controller.signal.aborted) return;
      setMoreError(readError(error, "后续榜位加载失败，请重试。").message);
    } finally {
      if (!controller.signal.aborted) {
        entriesMorePending.current = false;
        setLoadingEntriesMore(false);
      }
    }
  }

  if (sources.status === "loading")
    return (
      <PageState
        navigation={<WorkspaceHeader current="hotlists" />}
        eyebrow="热榜历史"
        title="正在加载来源"
        description="正在读取已应用的热榜来源。"
      />
    );
  if (sources.status === "error")
    return (
      <PageState
        navigation={<WorkspaceHeader current="hotlists" />}
        eyebrow="加载失败"
        title="暂时无法打开热榜"
        description={
          sources.requestId
            ? `${sources.message} 请求编号：${sources.requestId}`
            : sources.message
        }
        action={
          <Button onClick={() => window.location.reload()}>
            <RotateCcwIcon data-icon="inline-start" />
            重新加载
          </Button>
        }
      />
    );

  return (
    <div className="bg-background min-h-screen">
      <WorkspaceHeader current="hotlists" />
      <main className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
        <h1 className="mt-3 text-3xl font-normal tracking-tight sm:text-4xl">
          热榜
        </h1>
        <p className="text-muted-foreground mt-4 max-w-2xl leading-7">
          选择来源，查看已保存的热榜与排名变化。
        </p>
        {sources.items.length > 0 ? (
          <FieldGroup className="mt-8 max-w-sm">
            <Field>
              <FieldLabel htmlFor="hotlist-source">来源</FieldLabel>
              <Select value={activeSource ?? ""} onValueChange={selectSource}>
                <SelectTrigger id="hotlist-source" className="w-full">
                  <SelectValue placeholder="选择来源" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {sources.items.map((source) => (
                      <SelectItem
                        key={source.source_key}
                        value={source.source_key}
                      >
                        {SOURCES.find((item) => item.key === source.source_key)
                          ?.label ?? source.source_key}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
          </FieldGroup>
        ) : null}
        {!activeSource || sources.items.length === 0 ? (
          <InlineState
            eyebrow="尚无来源"
            title="还没有应用热榜来源"
            description="热榜来源配置并成功采集后，这里会显示历史快照。"
          />
        ) : !applied ? (
          <InlineState
            eyebrow="来源不可用"
            title="此来源尚未应用"
            description="该热榜尚未配置。请选择已启用的来源，或查看来源设置。"
            action={
              <Button asChild>
                <Link href="/sources">查看来源状态</Link>
              </Button>
            }
          />
        ) : history?.status === "error" &&
          history.sourceKey === activeSource ? (
          <InlineState
            eyebrow="加载失败"
            title="无法读取历史快照"
            description={
              history.requestId
                ? `${history.message} 请求编号：${history.requestId}`
                : history.message
            }
            action={
              <Button
                onClick={() => {
                  setHistory(null);
                  setHistoryRefresh((value) => value + 1);
                }}
              >
                重新加载
              </Button>
            }
          />
        ) : history?.status !== "ready" ||
          history.sourceKey !== activeSource ? (
          <div
            aria-label="正在读取历史快照"
            className="mt-10 flex flex-col gap-3"
          >
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-28 w-full" />
          </div>
        ) : history.items.length === 0 ? (
          <InlineState
            eyebrow="尚无快照"
            title="还没有成功的榜单快照"
            description="采集任务成功后，这里会出现按观察时间排序的历史记录。失败的采集不会伪装为空榜。"
          />
        ) : (
          <>
            <div className="mt-10">
              <SnapshotSelector
                snapshots={history.items}
                selectedId={selectedSnapshot ?? ""}
                nextCursor={history.nextCursor}
                loadingMore={loadingHistoryMore}
                onSelect={selectSnapshot}
                onLoadMore={() => void loadHistoryMore()}
              />
            </div>
            {detail?.status === "ready" &&
            detail.snapshotId === selectedSnapshot ? (
              <>
                <SnapshotDetail snapshot={detail.value} />
                {detail.value.next_cursor ? (
                  <div className="mt-8 flex justify-center">
                    <Button
                      variant="secondary"
                      onClick={() => void loadEntriesMore()}
                      disabled={loadingEntriesMore}
                    >
                      {loadingEntriesMore ? "正在加载" : "加载更多榜位"}
                    </Button>
                  </div>
                ) : null}
              </>
            ) : detail?.status === "error" &&
              detail.snapshotId === selectedSnapshot ? (
              <InlineState
                eyebrow={detail.forbidden ? "不可访问" : "加载失败"}
                title={
                  detail.forbidden ? "快照不存在或无权访问" : "无法读取快照"
                }
                description={
                  detail.requestId
                    ? `${detail.message} 请求编号：${detail.requestId}`
                    : detail.message
                }
                action={
                  <Button
                    onClick={() => {
                      setDetail(null);
                      setDetailRefresh((value) => value + 1);
                    }}
                  >
                    重新加载
                  </Button>
                }
              />
            ) : (
              <div
                aria-label="正在读取榜位"
                className="mt-10 flex flex-col gap-3"
              >
                <Skeleton className="h-28 w-full" />
                <Skeleton className="h-28 w-full" />
              </div>
            )}
            {moreError ? (
              <p role="alert" className="text-destructive mt-4 text-sm">
                {moreError}
              </p>
            ) : null}
          </>
        )}
      </main>
    </div>
  );
}
