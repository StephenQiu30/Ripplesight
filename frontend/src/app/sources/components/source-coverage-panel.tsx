"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { RotateCcwIcon, XIcon } from "lucide-react";

import {
  getCollectionCoverage,
  getCollectionCoverageMetrics,
  listCollectionCoverage,
} from "@/api/caijifugai";
import { listSourceCapabilities } from "@/api/laiyuannengli";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  const params = new URLSearchParams({
    tab: "coverage",
    start: query.start,
    end: query.end,
  });
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
    <Alert variant="destructive" className="mt-5">
      <AlertTitle>
        {failure.kind === "forbidden" ? "记录不存在或无权查看" : title}
      </AlertTitle>
      <AlertDescription>
        <p>
          {failure.message}
          {failure.requestId ? ` 请求编号：${failure.requestId}` : ""}
        </p>
        {failure.kind === "error" ? (
          <Button type="button" size="sm" variant="outline" onClick={onRetry}>
            <RotateCcwIcon data-icon="inline-start" />
            重新加载
          </Button>
        ) : null}
      </AlertDescription>
    </Alert>
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
        热榜相位未完成冻结验证时，延迟结论与成功桶比例仅供核对。
      </p>
      {value.sources.length === 0 ? (
        <Empty className="mt-4">
          <EmptyHeader>
            <EmptyTitle>暂无指标样本</EmptyTitle>
            <EmptyDescription>当前筛选没有逐来源指标样本。</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {value.sources.map((source) => (
            <Card key={`${source.source_key}:${source.capability}`}>
              <CardHeader>
                <CardTitle asChild>
                  <h4>
                    {source.source_key} · {capabilityLabel(source.capability)}
                  </h4>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap items-start justify-between gap-2">
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
              </CardContent>
            </Card>
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
  const [sourcesFailure, setSourcesFailure] = useState<ReadFailure | null>(
    null,
  );
  const [sourcesRefresh, setSourcesRefresh] = useState(0);
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
  const detailOrigin = useRef<HTMLElement | null>(null);
  const refreshButton = useRef<HTMLButtonElement | null>(null);
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
        if (!controller.signal.aborted) {
          setSources(page.items);
          setSourcesFailure(null);
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setSourcesFailure(readFailure(error, "来源选项加载失败，请重试。"));
      });
    return () => controller.abort();
  }, [sourcesRefresh]);

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
  }, [applied, requestKey]);

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
        setDetail({
          key: detailKey,
          status: "error",
          failure: readFailure(error, "窗口详情加载失败，请重试。"),
        });
      });
    return () => controller.abort();
  }, [selectedWindow, detailKey]);

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

  const closeDetail = () => {
    if (applied) router.replace(coverageUrl(applied), { scroll: false });
    else {
      const params = new URLSearchParams(searchParams.toString());
      params.delete("window");
      router.replace(`/sources?${params.toString()}`, { scroll: false });
    }
  };
  const sourceOptions = sources.some(
    (source) => source.source_key === draft.sourceKey,
  )
    ? sources.map((source) => ({
        key: source.source_key,
        label: source.display_name,
      }))
    : [
        ...sources.map((source) => ({
          key: source.source_key,
          label: source.display_name,
        })),
        ...(draft.sourceKey
          ? [{ key: draft.sourceKey, label: draft.sourceKey }]
          : []),
      ];

  return (
    <section
      id="coverage"
      aria-labelledby="source-coverage-heading"
      className="flex flex-col gap-6"
    >
      <div className="flex flex-col gap-2">
        <h2 id="source-coverage-heading" className="text-xl font-medium">
          采集覆盖
        </h2>
        <p className="text-muted-foreground max-w-2xl text-sm leading-6">
          查看来源在指定时间内的采集记录。时间输入与列表均为北京时间。
        </p>
      </div>
      {sourcesFailure ? (
        <QueryFailure
          title="来源选项加载失败"
          failure={sourcesFailure}
          onRetry={() => setSourcesRefresh((count) => count + 1)}
        />
      ) : null}
      <form onSubmit={applyFilters}>
        <FieldGroup className="grid gap-5 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="coverage-source">来源</FieldLabel>
            <Select
              value={draft.sourceKey || "all"}
              onValueChange={(value) =>
                changeDraft({ sourceKey: value === "all" ? "" : value })
              }
            >
              <SelectTrigger id="coverage-source" className="w-full">
                <SelectValue placeholder="全部来源" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">全部来源</SelectItem>
                  {sourceOptions.map((source) => (
                    <SelectItem key={source.key} value={source.key}>
                      {source.label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="coverage-capability">能力</FieldLabel>
            <Select
              value={draft.capability || "all"}
              onValueChange={(value) =>
                changeDraft({
                  capability:
                    value === "all"
                      ? ""
                      : (value as HotKeyAPI.SourceCapability),
                })
              }
            >
              <SelectTrigger id="coverage-capability" className="w-full">
                <SelectValue placeholder="全部能力" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="all">全部能力</SelectItem>
                  {CAPABILITIES.map((capability) => (
                    <SelectItem key={capability} value={capability}>
                      {capabilityLabel(capability)}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
          <Field data-invalid={!!validation}>
            <FieldLabel htmlFor="coverage-start">开始 · 北京时间</FieldLabel>
            <Input
              id="coverage-start"
              type="datetime-local"
              value={draft.startLocal}
              onChange={(event) =>
                changeDraft({ startLocal: event.target.value })
              }
              required
              aria-invalid={!!validation}
              aria-describedby={validation ? "coverage-validation" : undefined}
            />
          </Field>
          <Field data-invalid={!!validation}>
            <FieldLabel htmlFor="coverage-end">结束 · 北京时间</FieldLabel>
            <Input
              id="coverage-end"
              type="datetime-local"
              value={draft.endLocal}
              onChange={(event) =>
                changeDraft({ endLocal: event.target.value })
              }
              required
              aria-invalid={!!validation}
              aria-describedby={validation ? "coverage-validation" : undefined}
            />
          </Field>
          <Field className="sm:col-span-2">
            <FieldDescription>
              时间范围不超过 31 天，包含起点，不包含终点。
            </FieldDescription>
            {validation ? (
              <FieldError id="coverage-validation">{validation}</FieldError>
            ) : null}
            <div>
              <Button type="submit">查询窗口</Button>
            </div>
          </Field>
        </FieldGroup>
      </form>
      {!applied ? (
        <Alert>
          <AlertTitle>请确认查询条件</AlertTitle>
          <AlertDescription>
            {searchParams.get("start") || searchParams.get("end")
              ? "URL 中的时间或筛选条件无效；请重新选择时间并查询。"
              : "正在准备最近 24 小时的覆盖查询…"}
          </AlertDescription>
        </Alert>
      ) : (
        <Tabs defaultValue="windows" className="gap-6">
          <TabsList variant="line" aria-label="覆盖结果">
            <TabsTrigger value="windows">到期窗口</TabsTrigger>
            <TabsTrigger value="metrics">指标核对</TabsTrigger>
          </TabsList>
          <TabsContent value="windows">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <p className="text-muted-foreground max-w-lg text-sm leading-6">
                没有任务的到期记录仍保留；未知计数不显示为 0。
              </p>
              <Button
                ref={refreshButton}
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setRefreshCount((count) => count + 1)}
              >
                <RotateCcwIcon data-icon="inline-start" />
                刷新
              </Button>
            </div>
            {!visibleList ? (
              <div
                aria-label="正在读取覆盖窗口"
                className="mt-5 flex flex-col gap-3"
              >
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : visibleList.status === "error" ? (
              <QueryFailure
                title="覆盖窗口加载失败"
                failure={visibleList.failure}
                onRetry={() => setRefreshCount((count) => count + 1)}
              />
            ) : visibleList.items.length === 0 ? (
              <Empty className="mt-5">
                <EmptyHeader>
                  <EmptyTitle>此筛选下暂无到期窗口</EmptyTitle>
                  <EmptyDescription>
                    这只表示账本没有对应到期记录，不代表来源采集完整。
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <>
                {visibleList.items.some(
                  (row) =>
                    !["complete", "empty"].includes(row.coverage_status) ||
                    row.gaps.length > 0,
                ) ? (
                  <p
                    role="status"
                    className="text-muted-foreground mt-5 text-sm"
                  >
                    列表含未完成、失败或未确认缺口的窗口，请逐项打开核对。
                  </p>
                ) : null}
                <CoverageWindowTable
                  items={visibleList.items}
                  selectedId={selectedWindow}
                  onSelect={(id) => {
                    detailOrigin.current =
                      document.activeElement instanceof HTMLElement
                        ? document.activeElement
                        : null;
                    router.replace(coverageUrl(applied, id), { scroll: false });
                  }}
                />
                {visibleList.nextCursor ? (
                  <div className="mt-6 flex justify-center">
                    <Button
                      type="button"
                      variant="outline"
                      disabled={loadingMore}
                      onClick={() => void loadMore()}
                    >
                      {loadingMore ? "正在加载…" : "加载更多"}
                    </Button>
                  </div>
                ) : null}
                {moreError ? (
                  <Alert variant="destructive" className="mt-3">
                    <AlertTitle>后续窗口加载失败</AlertTitle>
                    <AlertDescription>{moreError}</AlertDescription>
                  </Alert>
                ) : null}
              </>
            )}
          </TabsContent>
          <TabsContent value="metrics">
            {!visibleMetrics ? (
              <div
                aria-label="正在读取逐来源指标"
                className="grid gap-3 sm:grid-cols-2"
              >
                <Skeleton className="h-36" />
                <Skeleton className="h-36" />
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
          </TabsContent>
        </Tabs>
      )}
      <Sheet
        open={!!selectedWindow}
        onOpenChange={(open) => {
          if (!open) closeDetail();
        }}
      >
        <SheetContent
          showCloseButton={false}
          className="overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-2xl"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            (detailOrigin.current?.isConnected
              ? detailOrigin.current
              : refreshButton.current
            )?.focus();
          }}
        >
          <SheetHeader className="pr-14">
            <SheetTitle>覆盖详情</SheetTitle>
            <SheetDescription>
              查看真实采集记录、未确认缺口和关联内容。
            </SheetDescription>
          </SheetHeader>
          <SheetClose asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              className="absolute top-3 right-3"
              aria-label="关闭覆盖详情"
            >
              <XIcon data-icon="inline-start" />
            </Button>
          </SheetClose>
          <div className="px-4 pb-8">
            {!visibleDetail ? (
              <Skeleton aria-label="正在读取窗口详情" className="h-64 w-full" />
            ) : visibleDetail.status === "error" ? (
              <QueryFailure
                title="窗口详情加载失败"
                failure={visibleDetail.failure}
                onRetry={() => setDetailRefreshCount((count) => count + 1)}
              />
            ) : applied && !windowMatchesQuery(visibleDetail.value, applied) ? (
              <Alert>
                <AlertTitle>窗口不属于当前筛选</AlertTitle>
                <AlertDescription>
                  请调整筛选条件，或关闭此详情。
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={closeDetail}
                  >
                    关闭详情
                  </Button>
                </AlertDescription>
              </Alert>
            ) : (
              <CoverageWindowDetail
                row={visibleDetail.value}
                onClose={closeDetail}
              />
            )}
          </div>
        </SheetContent>
      </Sheet>
    </section>
  );
}
