"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
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
import { safeExternalHref } from "@/app/content/components/content-presenters";
import { BrandLockup } from "@/components/brand/brand-lockup";
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

function readError(error: unknown, fallback: string) {
  return error instanceof ApiRequestError
    ? { message: error.message, requestId: error.requestId }
    : { message: fallback };
}

function invalidSession(error: unknown): boolean {
  return error instanceof ApiRequestError && error.code === "invalid_session";
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
    <section
      aria-label={title}
      className="bg-muted mt-10 rounded-2xl p-6 sm:p-8"
    >
      <Badge variant="secondary">{eyebrow}</Badge>
      <h2 className="mt-4 text-xl font-semibold">{title}</h2>
      <p className="text-muted-foreground mt-2 max-w-xl text-sm leading-6">
        {description}
      </p>
      {action ? <div className="mt-6">{action}</div> : null}
    </section>
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
        <h2 className="text-2xl font-semibold tracking-tight">
          {formatHotlistTime(snapshot.observed_at)}
        </h2>
        <Badge variant="secondary">{snapshot.entry_count} 条</Badge>
        {(snapshot.gap_count ?? 0) > 0 ? (
          <Badge variant="destructive">
            此前 {snapshot.gap_count} 个采集窗口无快照
          </Badge>
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
        <div className="bg-muted mt-8 rounded-2xl px-6 py-12">
          <h3 className="text-lg font-medium">本次观察到空榜</h3>
          <p className="text-muted-foreground mt-2 text-sm">
            这是一条成功的零条目快照。
          </p>
        </div>
      ) : (
        <ol className="mt-8 space-y-3">
          {snapshot.items.map((entry) => {
            const originalHref = safeExternalHref(entry.url);
            return (
              <li key={entry.rank} className="bg-muted rounded-2xl p-5 sm:p-6">
                <div className="flex items-start gap-4">
                  <span className="font-mono text-xl font-semibold tabular-nums">
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

  useEffect(() => {
    let current = true;
    void listHotlistSources()
      .then((page) => {
        if (current) setSources({ status: "ready", items: page.items });
      })
      .catch((error: unknown) => {
        if (!current) return;
        if (invalidSession(error)) {
          router.replace("/login");
          return;
        }
        setSources({
          status: "error",
          ...readError(error, "热榜来源加载失败，请重试。"),
        });
      });
    return () => {
      current = false;
    };
  }, [router]);

  const activeSource =
    requestedSource ??
    (sources.status === "ready" ? sources.items[0]?.source_key : null);
  const applied =
    sources.status === "ready" &&
    sources.items.some((item) => item.source_key === activeSource);

  useEffect(() => {
    if (!activeSource || !applied) return;
    const controller = new AbortController();
    void listHotlistSnapshots(
      { source_key: activeSource, limit: 20 },
      { signal: controller.signal },
    )
      .then((page) => {
        if (!controller.signal.aborted)
          setHistory({
            status: "ready",
            sourceKey: activeSource,
            items: page.items,
            nextCursor: page.next_cursor,
          });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (invalidSession(error)) {
          router.replace("/login");
          return;
        }
        setHistory({
          status: "error",
          sourceKey: activeSource,
          ...readError(error, "热榜历史加载失败，请重试。"),
        });
      });
    return () => controller.abort();
  }, [activeSource, applied, router, historyRefresh]);

  const selectedSnapshot =
    history?.status === "ready" && history.sourceKey === activeSource
      ? (requestedSnapshot ?? history.items[0]?.snapshot_id)
      : null;

  useEffect(() => {
    if (!activeSource || !selectedSnapshot) return;
    const controller = new AbortController();
    void resolveSnapshotRequest(
      activeSource,
      selectedSnapshot,
      controller.signal,
    )
      .then((snapshot) => {
        if (snapshot && !controller.signal.aborted)
          setDetail({
            status: "ready",
            snapshotId: selectedSnapshot,
            value: snapshot,
          });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (invalidSession(error)) {
          router.replace("/login");
          return;
        }
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
  }, [activeSource, selectedSnapshot, router, detailRefresh]);

  function selectSource(sourceKey: string) {
    router.replace(`/hotlists?source=${encodeURIComponent(sourceKey)}`);
  }

  function selectSnapshot(snapshotId: string) {
    if (!activeSource) return;
    router.replace(
      `/hotlists?source=${encodeURIComponent(activeSource)}&snapshot=${encodeURIComponent(snapshotId)}`,
    );
  }

  async function loadHistoryMore() {
    if (
      !activeSource ||
      history?.status !== "ready" ||
      history.sourceKey !== activeSource ||
      !history.nextCursor
    )
      return;
    setLoadingHistoryMore(true);
    setMoreError(null);
    try {
      const page = await listHotlistSnapshots({
        source_key: activeSource,
        cursor: history.nextCursor,
        limit: 20,
      });
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
      if (invalidSession(error)) router.replace("/login");
      else setMoreError(readError(error, "后续历史加载失败，请重试。").message);
    } finally {
      setLoadingHistoryMore(false);
    }
  }

  async function loadEntriesMore() {
    if (
      !activeSource ||
      !selectedSnapshot ||
      detail?.status !== "ready" ||
      detail.snapshotId !== selectedSnapshot ||
      !detail.value.next_cursor
    )
      return;
    setLoadingEntriesMore(true);
    setMoreError(null);
    try {
      const page = await getHistoricalHotlistSnapshot({
        source_key: activeSource,
        snapshot_id: selectedSnapshot,
        cursor: detail.value.next_cursor,
        limit: 20,
      });
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
      if (invalidSession(error)) router.replace("/login");
      else setMoreError(readError(error, "后续榜位加载失败，请重试。").message);
    } finally {
      setLoadingEntriesMore(false);
    }
  }

  if (sources.status === "loading")
    return (
      <PageState
        eyebrow="热榜历史"
        title="正在加载来源"
        description="正在读取已应用的热榜来源。"
      />
    );
  if (sources.status === "error")
    return (
      <PageState
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
      <header className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8 xl:px-16 2xl:px-0">
        <BrandLockup href="/events" compactOnMobile />
        <Button asChild variant="ghost">
          <Link href="/events">返回工作台</Link>
        </Button>
      </header>
      <main className="mx-auto max-w-7xl px-5 py-12 sm:px-8 sm:py-16 xl:px-16 2xl:px-0">
        <p className="text-muted-foreground text-sm">信息获取 / 热榜</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">
          六榜历史
        </h1>
        <p className="text-muted-foreground mt-4 max-w-2xl leading-7">
          按来源查看每次真实快照、排名变化和命中主题。观察时间与来源发布时间分开记录。
        </p>
        <nav aria-label="热榜来源" className="mt-8 flex flex-wrap gap-2">
          {SOURCES.map((source) => {
            const available = sources.items.some(
              (item) => item.source_key === source.key,
            );
            return (
              <Button
                key={source.key}
                type="button"
                variant={source.key === activeSource ? "default" : "secondary"}
                onClick={() => selectSource(source.key)}
                aria-current={source.key === activeSource ? "page" : undefined}
              >
                {source.label}
                {available ? "" : " · 未应用"}
              </Button>
            );
          })}
        </nav>
        {!activeSource || sources.items.length === 0 ? (
          <InlineState
            eyebrow="尚无来源"
            title="还没有应用热榜来源"
            description="应用热榜来源后，这里会显示真实采集的历史快照。"
          />
        ) : !applied ? (
          <InlineState
            eyebrow="来源不可用"
            title="此来源尚未应用"
            description="请在来源状态中应用该热榜，再查看快照。"
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
          <div aria-label="正在读取历史快照" className="mt-10 space-y-3">
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
              <div aria-label="正在读取榜位" className="mt-10 space-y-3">
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
