"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { RotateCcwIcon } from "lucide-react";

import {
  getCollectionCoverage,
  getCollectionCoverageMetrics,
  listCollectionCoverage,
} from "@/api/caijifugai";
import { listSourceCapabilities } from "@/api/laiyuannengli";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/request";

import { CoverageWindowDetail } from "./coverage-window-detail";
import {
  capabilityLabel,
  coverageTime,
  CoverageWindowTable,
} from "./coverage-window-table";

const SHANGHAI_OFFSET_MS = 8 * 60 * 60 * 1_000;
const MAX_RANGE_MS = 31 * 24 * 60 * 60 * 1_000;
const SOURCE_KEY_PATTERN = /^[a-z][a-z0-9_-]{0,63}$/;
const LOCAL_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const CAPABILITIES = [
  "search",
  "author_posts",
  "comments",
  "replies",
  "page_content",
  "hotlist",
] as const;

export type CoverageQuery = {
  start: string;
  end: string;
  sourceKey: string;
  capability: "" | HotKeyAPI.SourceCapability;
};

type CoverageDraft = {
  sourceKey: string;
  capability: CoverageQuery["capability"];
  startLocal: string;
  endLocal: string;
};

type ReadFailure = {
  kind: "error" | "forbidden";
  message: string;
  requestId?: string;
};

type ListState =
  | {
      key: string;
      status: "ready";
      items: HotKeyAPI.CollectionCoverageView[];
      nextCursor: string | null;
    }
  | { key: string; status: "error"; failure: ReadFailure };

type MetricsState =
  | {
      key: string;
      status: "ready";
      value: HotKeyAPI.CollectionCoverageMetricsView;
    }
  | { key: string; status: "error"; failure: ReadFailure };

type DetailState =
  | { key: string; status: "ready"; value: HotKeyAPI.CollectionCoverageView }
  | { key: string; status: "error"; failure: ReadFailure };

function readFailure(error: unknown, fallback: string): ReadFailure {
  if (error instanceof ApiRequestError) {
    return {
      kind:
        error.status === 403 || error.status === 404 ? "forbidden" : "error",
      message: error.message,
      requestId: error.requestId,
    };
  }
  return { kind: "error", message: fallback };
}

function invalidSession(error: unknown): boolean {
  return (
    error instanceof ApiRequestError &&
    (error.status === 401 || error.code === "invalid_session")
  );
}

export function shanghaiLocalToUtc(value: string): string | null {
  if (!LOCAL_TIME_PATTERN.test(value)) return null;
  const [date, time] = value.split("T");
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const wallTime = Date.UTC(year, month - 1, day, hour, minute);
  if (new Date(wallTime).toISOString().slice(0, 16) !== value) return null;
  return new Date(wallTime - SHANGHAI_OFFSET_MS).toISOString();
}

export function utcToShanghaiLocal(value: string): string | null {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return null;
  return new Date(timestamp + SHANGHAI_OFFSET_MS).toISOString().slice(0, 16);
}

export function parseCoverageQuery(
  params: URLSearchParams,
): CoverageQuery | null {
  const rawStart = params.get("start");
  const rawEnd = params.get("end");
  const sourceKey = params.get("source_key") ?? "";
  const capability = params.get("capability") ?? "";
  if (
    !rawStart ||
    !rawEnd ||
    !/(Z|[+-]\d{2}:\d{2})$/.test(rawStart) ||
    !/(Z|[+-]\d{2}:\d{2})$/.test(rawEnd) ||
    (sourceKey && !SOURCE_KEY_PATTERN.test(sourceKey))
  ) {
    return null;
  }
  if (capability && !CAPABILITIES.some((item) => item === capability))
    return null;
  const start = Date.parse(rawStart);
  const end = Date.parse(rawEnd);
  if (
    Number.isNaN(start) ||
    Number.isNaN(end) ||
    end <= start ||
    end - start > MAX_RANGE_MS
  ) {
    return null;
  }
  return {
    start: new Date(start).toISOString(),
    end: new Date(end).toISOString(),
    sourceKey,
    capability: capability as CoverageQuery["capability"],
  };
}

export function coverageQueryFromDraft(draft: CoverageDraft): {
  query: CoverageQuery | null;
  error: string | null;
} {
  const start = shanghaiLocalToUtc(draft.startLocal);
  const end = shanghaiLocalToUtc(draft.endLocal);
  if (draft.sourceKey && !SOURCE_KEY_PATTERN.test(draft.sourceKey)) {
    return {
      query: null,
      error: "来源键须以小写字母开头，只能包含小写字母、数字、下划线或连字符。",
    };
  }
  if (!start || !end) {
    return { query: null, error: "请选择有效的北京时间起点和终点。" };
  }
  const elapsed = Date.parse(end) - Date.parse(start);
  if (elapsed <= 0 || elapsed > MAX_RANGE_MS) {
    return { query: null, error: "时间范围须大于 0 且不超过 31 天。" };
  }
  return {
    query: {
      start,
      end,
      sourceKey: draft.sourceKey,
      capability: draft.capability,
    },
    error: null,
  };
}

export function coverageUrl(query: CoverageQuery, windowId?: string): string {
  const params = new URLSearchParams({ start: query.start, end: query.end });
  if (query.sourceKey) params.set("source_key", query.sourceKey);
  if (query.capability) params.set("capability", query.capability);
  if (windowId) params.set("window", windowId);
  return `/sources?${params.toString()}`;
}

function defaultQuery(): CoverageQuery {
  const end = Math.floor(Date.now() / 60_000) * 60_000;
  return {
    start: new Date(end - 24 * 60 * 60 * 1_000).toISOString(),
    end: new Date(end).toISOString(),
    sourceKey: "",
    capability: "",
  };
}

function queryDraft(query: CoverageQuery): CoverageDraft {
  return {
    sourceKey: query.sourceKey,
    capability: query.capability,
    startLocal: utcToShanghaiLocal(query.start) ?? "",
    endLocal: utcToShanghaiLocal(query.end) ?? "",
  };
}

function apiParams(
  query: CoverageQuery,
): HotKeyAPI.getCollectionCoverageMetricsParams {
  return {
    start: query.start,
    end: query.end,
    ...(query.sourceKey ? { source_key: query.sourceKey } : {}),
    ...(query.capability ? { capability: query.capability } : {}),
  };
}

export async function readCoveragePage(
  query: CoverageQuery,
  signal: AbortSignal,
  cursor?: string,
): Promise<HotKeyAPI.PageViewCollectionCoverageView_ | null> {
  const page = await listCollectionCoverage(
    { ...apiParams(query), limit: 20, ...(cursor ? { cursor } : {}) },
    { signal },
  );
  return signal.aborted ? null : page;
}

export function windowMatchesQuery(
  row: HotKeyAPI.CollectionCoverageView,
  query: CoverageQuery,
): boolean {
  const due = Date.parse(row.due_at);
  return (
    due >= Date.parse(query.start) &&
    due < Date.parse(query.end) &&
    (!query.sourceKey || row.source_key === query.sourceKey) &&
    (!query.capability || row.capability === query.capability)
  );
}

function QueryFailure({
  title,
  failure,
  onRetry,
}: {
  title: string;
  failure: ReadFailure;
  onRetry: () => void;
}) {
  return (
    <div className="bg-muted mt-5 rounded-2xl p-5" role="alert">
      <h3 className="font-medium">
        {failure.kind === "forbidden" ? "记录不存在或无权查看" : title}
      </h3>
      <p className="text-muted-foreground mt-2 text-sm">
        {failure.message}
        {failure.requestId ? ` 请求编号：${failure.requestId}` : ""}
      </p>
      {failure.kind === "error" ? (
        <Button
          className="mt-4"
          type="button"
          size="sm"
          variant="secondary"
          onClick={onRetry}
        >
          <RotateCcwIcon data-icon="inline-start" />
          重新加载
        </Button>
      ) : null}
    </div>
  );
}

const TIMING_LABELS: Record<
  HotKeyAPI.CollectionTimingMetricView["result"],
  string
> = {
  passed: "受控指标达标",
  failed: "指标未达标",
  indeterminate: "删失样本，暂不可判定",
  no_samples: "无合格样本",
};

function MetricSummary({
  value,
}: {
  value: HotKeyAPI.CollectionCoverageMetricsView;
}) {
  return (
    <section aria-labelledby="coverage-metrics-heading" className="mt-10">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 id="coverage-metrics-heading" className="text-lg font-semibold">
          逐来源指标
        </h3>
        <p className="text-muted-foreground text-xs">
          统计截止：{coverageTime(value.cutoff_at)}
        </p>
      </div>
      <p className="text-muted-foreground mt-2 text-sm">
        {value.analysis_status === "not_computable"
          ? "分析时效尚不可计算。"
          : `分析状态：${value.analysis_status}。`}
        热榜相位未完成冻结验证时，成功桶比例仅供核对。
      </p>
      {value.sources.length === 0 ? (
        <p className="bg-muted mt-4 rounded-2xl p-5 text-sm">
          当前筛选没有逐来源指标样本。
        </p>
      ) : (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {value.sources.map((source) => (
            <article
              key={`${source.source_key}:${source.capability}`}
              className="bg-muted rounded-2xl p-5"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h4 className="font-medium">
                  {source.source_key} · {capabilityLabel(source.capability)}
                </h4>
                <Badge
                  variant={
                    source.timing.result === "failed"
                      ? "destructive"
                      : "outline"
                  }
                >
                  {TIMING_LABELS[source.timing.result]}
                </Badge>
              </div>
              <p className="mt-3 text-sm">
                到期 {source.timing.due_count} · 排除{" "}
                {source.timing.excluded_count} · 超时{" "}
                {source.timing.timeout_count}
              </p>
              <p className="text-muted-foreground mt-1 text-sm">
                中位延迟：
                {source.timing.median_seconds === null
                  ? "未知"
                  : `${source.timing.median_seconds} 秒`}
                {source.timing.median_seconds === null &&
                source.timing.median_lower_bound_seconds !== null
                  ? `（下界 ${source.timing.median_lower_bound_seconds} 秒）`
                  : ""}
              </p>
              {source.hotlist ? (
                <p className="text-muted-foreground mt-2 text-sm">
                  热榜桶：成功 {source.hotlist.success_count} / 应到{" "}
                  {source.hotlist.expected_count}
                  {source.hotlist.phase_verified
                    ? " · 相位已验证"
                    : " · 相位未验证"}
                </p>
              ) : null}
              {source.exclusions.length > 0 ? (
                <p className="text-muted-foreground mt-2 text-xs">
                  排除依据：
                  {source.exclusions
                    .map(
                      (item) =>
                        `${item.reason} · ${item.evidence_id.slice(0, 8)}`,
                    )
                    .join("；")}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export function SourceCoveragePanel() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const paramsKey = searchParams.toString();
  const filterParams = new URLSearchParams(paramsKey);
  filterParams.delete("window");
  const filterKey = filterParams.toString();
  const applied = useMemo(
    () => parseCoverageQuery(new URLSearchParams(filterKey)),
    [filterKey],
  );
  const queryKey = applied ? coverageUrl(applied) : "";
  const selectedWindow = searchParams.get("window");
  const [draftState, setDraftState] = useState<{
    key: string;
    value: CoverageDraft;
  } | null>(null);
  const draft: CoverageDraft =
    draftState?.key === queryKey
      ? draftState.value
      : applied
        ? queryDraft(applied)
        : { sourceKey: "", capability: "", startLocal: "", endLocal: "" };
  const [validation, setValidation] = useState<string | null>(null);
  const [sources, setSources] = useState<HotKeyAPI.SourcePlatformView[]>([]);
  const [list, setList] = useState<ListState | null>(null);
  const [metrics, setMetrics] = useState<MetricsState | null>(null);
  const [detail, setDetail] = useState<DetailState | null>(null);
  const [refreshCount, setRefreshCount] = useState(0);
  const [detailRefreshCount, setDetailRefreshCount] = useState(0);
  const [loadMoreState, setLoadMoreState] = useState<{
    key: string;
    loading: boolean;
    error: string | null;
  } | null>(null);
  const pageController = useRef<AbortController | null>(null);
  const requestKey = `${queryKey}:${refreshCount}`;
  const detailKey = `${selectedWindow ?? ""}:${detailRefreshCount}`;
  const loadingMore =
    loadMoreState?.key === requestKey && loadMoreState.loading;
  const moreError =
    loadMoreState?.key === requestKey ? loadMoreState.error : null;

  useEffect(() => {
    if (!searchParams.get("start") && !searchParams.get("end")) {
      router.replace(coverageUrl(defaultQuery()), { scroll: false });
    }
  }, [paramsKey, router, searchParams]);

  useEffect(() => {
    const controller = new AbortController();
    void listSourceCapabilities({ signal: controller.signal })
      .then((page) => {
        if (!controller.signal.aborted) setSources(page.items);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && invalidSession(error))
          router.replace("/login");
      });
    return () => controller.abort();
  }, [router]);

  useEffect(() => {
    if (!applied) return;
    const controller = new AbortController();
    pageController.current?.abort();
    const params = apiParams(applied);
    void readCoveragePage(applied, controller.signal)
      .then((page) => {
        if (page && !controller.signal.aborted) {
          setList({
            key: requestKey,
            status: "ready",
            items: page.items,
            nextCursor: page.next_cursor,
          });
          setLoadMoreState(null);
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (invalidSession(error)) router.replace("/login");
        else
          setList({
            key: requestKey,
            status: "error",
            failure: readFailure(error, "覆盖窗口加载失败，请重试。"),
          });
      });
    void getCollectionCoverageMetrics(params, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted)
          setMetrics({ key: requestKey, status: "ready", value });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (invalidSession(error)) router.replace("/login");
        else
          setMetrics({
            key: requestKey,
            status: "error",
            failure: readFailure(error, "逐来源指标加载失败，请重试。"),
          });
      });
    return () => {
      controller.abort();
      pageController.current?.abort();
    };
  }, [applied, requestKey, router]);

  useEffect(() => {
    if (!selectedWindow) return;
    const controller = new AbortController();
    void getCollectionCoverage(
      { window_id: selectedWindow },
      { signal: controller.signal },
    )
      .then((value) => {
        if (!controller.signal.aborted)
          setDetail({ key: detailKey, status: "ready", value });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (invalidSession(error)) router.replace("/login");
        else
          setDetail({
            key: detailKey,
            status: "error",
            failure: readFailure(error, "窗口详情加载失败，请重试。"),
          });
      });
    return () => controller.abort();
  }, [selectedWindow, detailKey, router]);

  function changeDraft(change: Partial<CoverageDraft>) {
    setDraftState({ key: queryKey, value: { ...draft, ...change } });
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = coverageQueryFromDraft(draft);
    setValidation(result.error);
    if (result.query)
      router.replace(coverageUrl(result.query), { scroll: false });
  }

  async function loadMore() {
    if (
      !applied ||
      list?.status !== "ready" ||
      list.key !== requestKey ||
      !list.nextCursor ||
      loadingMore
    )
      return;
    const key = requestKey;
    const controller = new AbortController();
    pageController.current?.abort();
    pageController.current = controller;
    setLoadMoreState({ key, loading: true, error: null });
    try {
      const page = await readCoveragePage(
        applied,
        controller.signal,
        list.nextCursor,
      );
      if (!page || controller.signal.aborted) return;
      setList((current) =>
        current?.status === "ready" && current.key === key
          ? {
              ...current,
              items: [...current.items, ...page.items],
              nextCursor: page.next_cursor,
            }
          : current,
      );
    } catch (error) {
      if (controller.signal.aborted) return;
      if (invalidSession(error)) router.replace("/login");
      else
        setLoadMoreState({
          key,
          loading: false,
          error: readFailure(error, "后续窗口加载失败，请重试。").message,
        });
    } finally {
      if (!controller.signal.aborted)
        setLoadMoreState((current) =>
          current?.key === key ? { ...current, loading: false } : current,
        );
    }
  }

  const visibleList = list?.key === requestKey ? list : null;
  const visibleMetrics = metrics?.key === requestKey ? metrics : null;
  const visibleDetail = detail?.key === detailKey ? detail : null;

  return (
    <section
      id="coverage"
      aria-labelledby="source-coverage-heading"
      className="mt-12"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 id="source-coverage-heading" className="text-2xl font-semibold">
          采集覆盖
        </h2>
        <p className="text-muted-foreground text-xs">
          时间输入与列表显示均为北京时间
        </p>
      </div>
      <form
        onSubmit={applyFilters}
        className="bg-muted mt-5 grid gap-4 rounded-2xl p-5 sm:grid-cols-2 sm:p-6 lg:grid-cols-5"
      >
        <div className="space-y-2">
          <Label htmlFor="coverage-source">来源</Label>
          <Input
            id="coverage-source"
            list="coverage-source-options"
            value={draft.sourceKey}
            onChange={(event) =>
              changeDraft({ sourceKey: event.target.value.trim() })
            }
            placeholder="全部来源"
          />
          <datalist id="coverage-source-options">
            {sources.map((source) => (
              <option key={source.source_key} value={source.source_key}>
                {source.display_name}
              </option>
            ))}
          </datalist>
        </div>
        <div className="space-y-2">
          <Label htmlFor="coverage-capability">能力</Label>
          <select
            id="coverage-capability"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={draft.capability}
            onChange={(event) =>
              changeDraft({
                capability: event.target.value as CoverageDraft["capability"],
              })
            }
          >
            <option value="">全部能力</option>
            <option value="search">检索</option>
            <option value="author_posts">作者作品</option>
            <option value="comments">评论</option>
            <option value="replies">回复</option>
            <option value="page_content">页面正文</option>
            <option value="hotlist">热榜</option>
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="coverage-start">开始 · 北京时间</Label>
          <Input
            id="coverage-start"
            type="datetime-local"
            value={draft.startLocal}
            onChange={(event) =>
              changeDraft({ startLocal: event.target.value })
            }
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="coverage-end">结束 · 北京时间</Label>
          <Input
            id="coverage-end"
            type="datetime-local"
            value={draft.endLocal}
            onChange={(event) => changeDraft({ endLocal: event.target.value })}
            required
          />
        </div>
        <div className="flex items-end">
          <Button type="submit" className="w-full">
            查询窗口
          </Button>
        </div>
        {validation ? (
          <p
            className="text-destructive sm:col-span-2 lg:col-span-5"
            role="alert"
          >
            {validation}
          </p>
        ) : null}
      </form>

      {!applied ? (
        <div className="bg-muted mt-6 rounded-2xl p-6" role="status">
          {searchParams.get("start") || searchParams.get("end")
            ? "URL 中的时间或筛选条件无效；请重新选择时间并查询。"
            : "正在准备最近 24 小时的覆盖查询…"}
        </div>
      ) : (
        <>
          <div className="mt-10 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h3 className="text-lg font-semibold">到期窗口</h3>
              <p className="text-muted-foreground mt-1 text-sm">
                没有 Job 的到期点仍保留；未知计数不显示为 0。
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => setRefreshCount((count) => count + 1)}
            >
              <RotateCcwIcon data-icon="inline-start" />
              刷新
            </Button>
          </div>
          {!visibleList ? (
            <div aria-label="正在读取覆盖窗口" className="mt-5 space-y-3">
              <Skeleton className="h-16 w-full rounded-2xl" />
              <Skeleton className="h-16 w-full rounded-2xl" />
              <Skeleton className="h-16 w-full rounded-2xl" />
            </div>
          ) : visibleList.status === "error" ? (
            <QueryFailure
              title="覆盖窗口加载失败"
              failure={visibleList.failure}
              onRetry={() => setRefreshCount((count) => count + 1)}
            />
          ) : visibleList.items.length === 0 ? (
            <div className="bg-muted mt-5 rounded-2xl p-6">
              <h4 className="font-medium">此筛选下暂无到期窗口</h4>
              <p className="text-muted-foreground mt-2 text-sm">
                这只表示账本没有对应到期记录，不代表来源采集完整。
              </p>
            </div>
          ) : (
            <>
              {visibleList.items.some(
                (row) =>
                  !["complete", "empty"].includes(row.coverage_status) ||
                  row.gaps.length > 0,
              ) ? (
                <p role="status" className="text-muted-foreground mt-5 text-sm">
                  列表含未完成、失败或未确认缺口的窗口，请逐项打开核对。
                </p>
              ) : null}
              <CoverageWindowTable
                items={visibleList.items}
                selectedId={selectedWindow}
                onSelect={(id) =>
                  router.replace(coverageUrl(applied, id), { scroll: false })
                }
              />
              {visibleList.nextCursor ? (
                <div className="mt-6 flex justify-center">
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={loadingMore}
                    onClick={() => void loadMore()}
                  >
                    {loadingMore ? "正在加载" : "加载更多"}
                  </Button>
                </div>
              ) : null}
              {moreError ? (
                <p
                  className="text-destructive mt-3 text-center text-sm"
                  role="alert"
                >
                  {moreError}
                </p>
              ) : null}
            </>
          )}

          {selectedWindow ? (
            !visibleDetail ? (
              <Skeleton
                aria-label="正在读取窗口详情"
                className="mt-8 h-64 w-full rounded-2xl"
              />
            ) : visibleDetail.status === "error" ? (
              <QueryFailure
                title="窗口详情加载失败"
                failure={visibleDetail.failure}
                onRetry={() => setDetailRefreshCount((count) => count + 1)}
              />
            ) : applied && !windowMatchesQuery(visibleDetail.value, applied) ? (
              <div className="bg-muted mt-8 rounded-2xl p-6" role="alert">
                <h3 className="font-medium">窗口不属于当前筛选</h3>
                <p className="text-muted-foreground mt-2 text-sm">
                  请调整筛选条件，或关闭此详情。
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="mt-4"
                  onClick={() =>
                    router.replace(coverageUrl(applied), { scroll: false })
                  }
                >
                  关闭详情
                </Button>
              </div>
            ) : (
              <CoverageWindowDetail
                row={visibleDetail.value}
                onClose={() =>
                  router.replace(coverageUrl(applied), { scroll: false })
                }
              />
            )
          ) : null}

          {!visibleMetrics ? (
            <div
              aria-label="正在读取逐来源指标"
              className="mt-10 grid gap-3 md:grid-cols-2"
            >
              <Skeleton className="h-36 rounded-2xl" />
              <Skeleton className="h-36 rounded-2xl" />
            </div>
          ) : visibleMetrics.status === "error" ? (
            <QueryFailure
              title="逐来源指标加载失败"
              failure={visibleMetrics.failure}
              onRetry={() => setRefreshCount((count) => count + 1)}
            />
          ) : (
            <MetricSummary value={visibleMetrics.value} />
          )}
        </>
      )}
    </section>
  );
}
