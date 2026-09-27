"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { ArrowRightIcon, ExternalLinkIcon, RotateCcwIcon } from "lucide-react";

import { listContentRecords } from "@/api/zuopinziliao";
import { listMonitorTopics } from "@/api/jiankongzhuti";
import { listSourceCapabilities } from "@/api/laiyuannengli";
import {
  contentScopeLabel,
  contentScopeNotice,
  formatMetric,
  formatTime,
  hasUnknownMetrics,
  safeExternalHref,
  visibilityStatusLabel,
  visibilityStatusNotice,
} from "@/app/content/components/content-presenters";
import { WebPageCaptureForm } from "@/app/content/components/webpage-capture-form";
import { BrandLockup } from "@/components/brand/brand-lockup";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiRequestError } from "@/request";

type ContentListState =
  | { status: "loading" }
  | {
      status: "ready";
      items: HotKeyAPI.ContentRecordSummaryView[];
      nextCursor: string | null;
    }
  | { status: "error"; message: string; requestId?: string };

type AnalysisFilter =
  "" | NonNullable<HotKeyAPI.listContentRecordsParams["analysis_state"]>;

type ContentFilters = {
  sourceKey: string;
  topicId: string;
  startDate: string;
  endDate: string;
  analysisState: AnalysisFilter;
};

const EMPTY_FILTERS: ContentFilters = {
  sourceKey: "",
  topicId: "",
  startDate: "",
  endDate: "",
  analysisState: "",
};

type FilterOptions =
  | { status: "loading" }
  | {
      status: "ready";
      topics: HotKeyAPI.MonitorTopicView[];
      sources: HotKeyAPI.SourcePlatformView[];
    }
  | { status: "error" };

async function fetchFilterOptions(): Promise<
  Extract<FilterOptions, { status: "ready" }>
> {
  const [sourcePage, topics] = await Promise.all([
    listSourceCapabilities(),
    (async () => {
      const all: HotKeyAPI.MonitorTopicView[] = [];
      let cursor: string | null = null;
      do {
        const page = await listMonitorTopics({
          include_archived: true,
          limit: 50,
          ...(cursor ? { cursor } : {}),
        });
        all.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor !== null);
      return all;
    })(),
  ]);
  return { status: "ready", sources: sourcePage.items, topics };
}

export function contentListParams(
  filters: ContentFilters,
  cursor?: string,
): HotKeyAPI.listContentRecordsParams {
  if (Boolean(filters.startDate) !== Boolean(filters.endDate)) {
    throw new Error("请选择完整的开始和结束日期。");
  }
  let startsAt: string | undefined;
  let endsAt: string | undefined;
  if (filters.startDate && filters.endDate) {
    const start = new Date(`${filters.startDate}T00:00:00+08:00`);
    const end = new Date(`${filters.endDate}T00:00:00+08:00`);
    end.setUTCDate(end.getUTCDate() + 1);
    const days = (end.getTime() - start.getTime()) / 86_400_000;
    if (
      !Number.isFinite(start.getTime()) ||
      !Number.isFinite(end.getTime()) ||
      days <= 0 ||
      days > 31
    ) {
      throw new Error("日期范围须按先后选择，且最多 31 天。");
    }
    startsAt = start.toISOString();
    endsAt = end.toISOString();
  }
  if (filters.analysisState && !filters.topicId) {
    throw new Error("先选择主题，再筛选标注状态。");
  }
  return {
    limit: 20,
    ...(cursor ? { cursor } : {}),
    ...(filters.sourceKey ? { source_key: filters.sourceKey } : {}),
    ...(filters.topicId ? { topic_id: filters.topicId } : {}),
    ...(startsAt ? { starts_at: startsAt, ends_at: endsAt } : {}),
    ...(filters.analysisState
      ? {
          analysis_state: filters.analysisState,
        }
      : {}),
  };
}

const ANALYSIS_LABELS: Record<
  Exclude<
    NonNullable<HotKeyAPI.ContentRecordSummaryView["analysis_state"]>,
    "valid"
  >,
  string
> = {
  missing: "暂无标注记录",
  pending: "等待标注",
  failed: "标注失败",
  invalid: "标注无效",
};

export function ContentAnalysisStatus({
  content,
}: {
  content: HotKeyAPI.ContentRecordSummaryView;
}) {
  if (content.analysis_state == null) return null;
  const label =
    content.analysis_state === "valid"
      ? content.analysis_relevant
        ? "相关"
        : "不相关"
      : ANALYSIS_LABELS[content.analysis_state];
  return (
    <Badge
      variant={content.analysis_state === "valid" ? "secondary" : "outline"}
    >
      {label}
    </Badge>
  );
}

export function TimelineBasis({
  content,
}: {
  content: HotKeyAPI.ContentRecordSummaryView;
}) {
  const label =
    content.timeline_basis === "published_at"
      ? "发布时间"
      : content.timeline_basis === "first_observed_at"
        ? "首次发现"
        : "时间未知";
  return (
    <span>
      {label}：{formatTime(content.timeline_at ?? null)}
    </span>
  );
}

function isInvalidSession(error: unknown): boolean {
  return error instanceof ApiRequestError && error.code === "invalid_session";
}

function toErrorState(
  error: unknown,
): Extract<ContentListState, { status: "error" }> {
  return error instanceof ApiRequestError
    ? { status: "error", message: error.message, requestId: error.requestId }
    : { status: "error", message: "作品资料加载失败，请稍后重试。" };
}

function ContentStatus({
  content,
}: {
  content: HotKeyAPI.ContentRecordSummaryView;
}) {
  return hasUnknownMetrics(content.latest_observation.metrics) ? (
    <Badge variant="outline">部分指标未知</Badge>
  ) : (
    <Badge variant="secondary">指标已记录</Badge>
  );
}

function VisibilityStatus({
  visibility,
}: {
  visibility: HotKeyAPI.ContentVisibilityView | null;
}) {
  if (visibility === null) {
    return <Badge variant="outline">来源状态未观察</Badge>;
  }
  const variant =
    visibility.status === "visible"
      ? "secondary"
      : visibility.status === "deleted" || visibility.status === "restricted"
        ? "destructive"
        : "outline";
  return (
    <Badge variant={variant}>{visibilityStatusLabel(visibility.status)}</Badge>
  );
}

function VisibilityNotice({
  visibility,
}: {
  visibility: HotKeyAPI.ContentVisibilityView | null;
}) {
  if (visibility === null || visibility.status === "visible") {
    return null;
  }
  return (
    <p className="text-muted-foreground mt-2 text-xs leading-5">
      {visibilityStatusNotice(visibility.status)}
    </p>
  );
}

function OriginalContentLink({
  canonicalUrl,
}: {
  canonicalUrl: string | null;
}) {
  const href = safeExternalHref(canonicalUrl);
  if (href === null) {
    return null;
  }

  return (
    <a
      className="text-muted-foreground mt-3 inline-flex items-center gap-1 text-xs underline underline-offset-4"
      href={href}
      target="_blank"
      rel="noreferrer"
    >
      打开原文
      <ExternalLinkIcon className="size-3" aria-hidden="true" />
    </a>
  );
}

function PrimaryMetrics({ metrics }: { metrics: HotKeyAPI.ContentMetricView }) {
  return (
    <span className="text-muted-foreground text-xs leading-5">
      点赞 {formatMetric(metrics.like_count)} · 评论{" "}
      {formatMetric(metrics.comment_count)} · 转发{" "}
      {formatMetric(metrics.repost_count)}
    </span>
  );
}

function ContentVersionSummary({
  version,
}: {
  version: HotKeyAPI.ContentVersionView | null;
}) {
  if (version === null) {
    return <p className="text-muted-foreground mt-2 text-xs">未取得正文</p>;
  }
  const preview = version.title ?? version.body;
  const notice = contentScopeNotice(version.text_scope);
  return (
    <div className="mt-2 min-w-0">
      <Badge variant="secondary">{contentScopeLabel(version.text_scope)}</Badge>
      {preview ? (
        <p className="mt-2 line-clamp-2 text-sm break-words whitespace-pre-wrap">
          {preview}
        </p>
      ) : null}
      {notice ? (
        <p className="text-muted-foreground mt-1 line-clamp-2 text-xs">
          {notice}
        </p>
      ) : null}
    </div>
  );
}

function LoadingContentList() {
  return (
    <div aria-label="正在读取作品资料" className="mt-8 space-y-3">
      {[0, 1, 2].map((item) => (
        <Skeleton key={item} className="h-24 w-full rounded-2xl" />
      ))}
    </div>
  );
}

export function ContentList() {
  const router = useRouter();
  const [state, setState] = useState<ContentListState>({ status: "loading" });
  const [options, setOptions] = useState<FilterOptions>({ status: "loading" });
  const [draft, setDraft] = useState<ContentFilters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<ContentFilters>(EMPTY_FILTERS);
  const [filterError, setFilterError] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const requestGeneration = useRef(0);

  const loadOptions = useCallback(async () => {
    setOptions({ status: "loading" });
    try {
      setOptions(await fetchFilterOptions());
    } catch (error) {
      if (isInvalidSession(error)) {
        router.replace("/login");
      } else {
        setOptions({ status: "error" });
      }
    }
  }, [router]);

  const load = useCallback(
    async (filters: ContentFilters) => {
      const generation = ++requestGeneration.current;
      setState({ status: "loading" });
      setIsLoadingMore(false);
      setLoadMoreError(null);
      try {
        const page = await listContentRecords(contentListParams(filters));
        if (generation !== requestGeneration.current) return;
        setState({
          status: "ready",
          items: page.items,
          nextCursor: page.next_cursor,
        });
      } catch (error) {
        if (generation !== requestGeneration.current) return;
        if (isInvalidSession(error)) {
          router.replace("/login");
          return;
        }
        setState(toErrorState(error));
      }
    },
    [router],
  );

  useEffect(() => {
    let active = true;
    const generation = ++requestGeneration.current;
    void listContentRecords(contentListParams(EMPTY_FILTERS))
      .then((page) => {
        if (active && generation === requestGeneration.current) {
          setState({
            status: "ready",
            items: page.items,
            nextCursor: page.next_cursor,
          });
        }
      })
      .catch((error: unknown) => {
        if (!active || generation !== requestGeneration.current) return;
        if (isInvalidSession(error)) router.replace("/login");
        else setState(toErrorState(error));
      });
    void fetchFilterOptions()
      .then((value) => {
        if (active) setOptions(value);
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (isInvalidSession(error)) router.replace("/login");
        else setOptions({ status: "error" });
      });
    return () => {
      active = false;
      requestGeneration.current += 1;
    };
  }, [router]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      contentListParams(draft);
      setFilterError(null);
      setApplied(draft);
      void load(draft);
    } catch (error) {
      setFilterError(error instanceof Error ? error.message : "筛选条件无效。");
    }
  }

  async function loadMore() {
    if (
      state.status !== "ready" ||
      state.nextCursor === null ||
      isLoadingMore
    ) {
      return;
    }
    setIsLoadingMore(true);
    setLoadMoreError(null);
    const generation = requestGeneration.current;
    try {
      const page = await listContentRecords(
        contentListParams(applied, state.nextCursor),
      );
      if (generation !== requestGeneration.current) return;
      setState((current) =>
        current.status === "ready"
          ? {
              status: "ready",
              items: [...current.items, ...page.items],
              nextCursor: page.next_cursor,
            }
          : current,
      );
    } catch (error) {
      if (generation !== requestGeneration.current) return;
      if (isInvalidSession(error)) {
        router.replace("/login");
      } else {
        setLoadMoreError(
          error instanceof ApiRequestError
            ? error.message
            : "后续作品加载失败，请重试。",
        );
      }
    } finally {
      if (generation === requestGeneration.current) setIsLoadingMore(false);
    }
  }

  return (
    <div className="bg-background min-h-screen">
      <header className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8 xl:px-16 2xl:px-0">
        <BrandLockup href="/events" />
        <Button asChild variant="ghost" size="navigation">
          <Link href="/events">返回工作台</Link>
        </Button>
      </header>

      <main className="mx-auto max-w-7xl px-5 py-12 sm:px-8 sm:py-16 xl:px-16 2xl:px-0">
        <p className="text-muted-foreground font-mono text-xs tracking-wider uppercase">
          Content
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          作品资料
        </h1>
        <p className="text-muted-foreground mt-4 max-w-2xl leading-7">
          查看已持久保存且仍可读的作品身份、正文边界与最近观察。摘要、截断和未知保持原语义，读取不会触发来源请求。
        </p>

        <WebPageCaptureForm />

        <form
          onSubmit={applyFilters}
          aria-label="筛选作品资料"
          className="bg-muted mt-8 rounded-2xl p-5 sm:p-6"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="font-medium">筛选已保存的作品</h2>
              <p className="text-muted-foreground mt-1 text-xs leading-5">
                日期按北京时间，结束日期包含当日；无发布时间时按首次发现时间筛选。
              </p>
            </div>
            {options.status === "error" ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => void loadOptions()}
              >
                重试加载筛选项
              </Button>
            ) : null}
          </div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <div className="space-y-2">
              <Label htmlFor="content-source">来源</Label>
              <select
                id="content-source"
                value={draft.sourceKey}
                onChange={(event) =>
                  setDraft({ ...draft, sourceKey: event.target.value })
                }
                disabled={options.status !== "ready"}
                className="border-input bg-background focus-visible:ring-ring h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none disabled:opacity-50"
              >
                <option value="">全部来源</option>
                {options.status === "ready"
                  ? options.sources.map((source) => (
                      <option key={source.source_key} value={source.source_key}>
                        {source.display_name}
                      </option>
                    ))
                  : null}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="content-topic">主题</Label>
              <select
                id="content-topic"
                value={draft.topicId}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    topicId: event.target.value,
                    analysisState: "",
                  })
                }
                disabled={options.status !== "ready"}
                className="border-input bg-background focus-visible:ring-ring h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none disabled:opacity-50"
              >
                <option value="">全部主题</option>
                {options.status === "ready"
                  ? options.topics.map((topic) => (
                      <option key={topic.id} value={topic.id}>
                        {topic.name}
                        {topic.status === "archived" ? "（已归档）" : ""}
                      </option>
                    ))
                  : null}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="content-start-date">开始日期</Label>
              <Input
                id="content-start-date"
                type="date"
                value={draft.startDate}
                onChange={(event) =>
                  setDraft({ ...draft, startDate: event.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="content-end-date">结束日期（含）</Label>
              <Input
                id="content-end-date"
                type="date"
                value={draft.endDate}
                onChange={(event) =>
                  setDraft({ ...draft, endDate: event.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="content-analysis-state">标注状态</Label>
              <select
                id="content-analysis-state"
                value={draft.analysisState}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    analysisState: event.target.value as AnalysisFilter,
                  })
                }
                disabled={!draft.topicId}
                className="border-input bg-background focus-visible:ring-ring h-10 w-full rounded-md border px-3 text-sm focus-visible:ring-2 focus-visible:outline-none disabled:opacity-50"
              >
                <option value="">全部状态</option>
                <option value="missing">暂无标注记录</option>
                <option value="pending">等待标注</option>
                <option value="failed">标注失败</option>
                <option value="invalid">标注无效</option>
                <option value="valid">已有有效结论</option>
              </select>
            </div>
          </div>
          {options.status === "error" ? (
            <p role="alert" className="text-destructive mt-3 text-sm">
              来源和主题暂时无法加载，日期筛选仍可使用。
            </p>
          ) : null}
          {filterError ? (
            <p role="alert" className="text-destructive mt-3 text-sm">
              {filterError}
            </p>
          ) : null}
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button type="submit">应用筛选</Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setDraft(EMPTY_FILTERS);
                setApplied(EMPTY_FILTERS);
                setFilterError(null);
                void load(EMPTY_FILTERS);
              }}
            >
              清除筛选
            </Button>
            {JSON.stringify(draft) !== JSON.stringify(applied) ? (
              <span className="text-muted-foreground text-xs">
                条件尚未应用
              </span>
            ) : null}
          </div>
        </form>

        {state.status === "error" ? (
          <section className="bg-destructive/10 mt-8 rounded-2xl p-6 sm:p-8">
            <h2 className="text-lg font-medium">暂时无法读取作品</h2>
            <p className="text-muted-foreground mt-2 text-sm leading-6">
              {state.message}
              {state.requestId ? ` 请求编号：${state.requestId}` : null}
            </p>
            <Button className="mt-5" onClick={() => void load(applied)}>
              <RotateCcwIcon data-icon="inline-start" />
              重新加载
            </Button>
          </section>
        ) : null}

        {state.status === "loading" ? <LoadingContentList /> : null}

        {state.status === "ready" && state.items.length === 0 ? (
          <section className="bg-muted mt-8 rounded-2xl px-6 py-14 text-center sm:px-10">
            <h2 className="text-lg font-medium">当前条件下没有可读作品</h2>
            <p className="text-muted-foreground mx-auto mt-2 max-w-md text-sm leading-6">
              完成受控采集并持久保存后，作品会显示在这里；当前为空不代表来源返回了零结果。
            </p>
          </section>
        ) : null}

        {state.status === "ready" && state.items.length > 0 ? (
          <>
            <div className="mt-8 hidden md:block">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>作品身份</TableHead>
                    <TableHead>最近观察</TableHead>
                    <TableHead>指标</TableHead>
                    <TableHead>发现依据</TableHead>
                    <TableHead className="text-right">查看</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {state.items.map((content) => (
                    <TableRow key={content.id}>
                      <TableCell className="max-w-xs whitespace-normal">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="outline">{content.source_key}</Badge>
                          <ContentStatus content={content} />
                          <ContentAnalysisStatus content={content} />
                          <VisibilityStatus
                            visibility={content.current_visibility}
                          />
                        </div>
                        <p className="mt-2 font-mono text-xs break-all">
                          {content.external_id}
                        </p>
                        <ContentVersionSummary
                          version={
                            content.latest_observation.content_version ?? null
                          }
                        />
                        <VisibilityNotice
                          visibility={content.current_visibility}
                        />
                        <p className="text-muted-foreground mt-1 text-xs">
                          作者：
                          {content.latest_observation.author_external_id ??
                            "未知"}
                        </p>
                      </TableCell>
                      <TableCell className="whitespace-normal">
                        <p>
                          {formatTime(content.latest_observation.observed_at)}
                        </p>
                        <p className="text-muted-foreground mt-1 text-xs">
                          发布：
                          {formatTime(content.latest_observation.published_at)}
                        </p>
                        <p className="text-muted-foreground mt-1 text-xs">
                          <TimelineBasis content={content} />
                        </p>
                      </TableCell>
                      <TableCell className="max-w-xs whitespace-normal">
                        <PrimaryMetrics
                          metrics={content.latest_observation.metrics}
                        />
                      </TableCell>
                      <TableCell>{content.discovery_count}</TableCell>
                      <TableCell className="text-right">
                        <Button asChild variant="ghost" size="sm">
                          <Link href={`/content/${content.id}`}>
                            详情
                            <ArrowRightIcon data-icon="inline-end" />
                          </Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <div className="mt-8 grid gap-3 md:hidden">
              {state.items.map((content) => (
                <article key={content.id} className="bg-muted rounded-2xl p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{content.source_key}</Badge>
                    <ContentStatus content={content} />
                    <ContentAnalysisStatus content={content} />
                    <VisibilityStatus visibility={content.current_visibility} />
                  </div>
                  <h2 className="mt-4 font-mono text-sm font-medium break-all">
                    {content.external_id}
                  </h2>
                  <ContentVersionSummary
                    version={content.latest_observation.content_version ?? null}
                  />
                  <VisibilityNotice visibility={content.current_visibility} />
                  <p className="text-muted-foreground mt-2 text-xs">
                    作者：
                    {content.latest_observation.author_external_id ?? "未知"}
                  </p>
                  <p className="text-muted-foreground mt-1 text-xs">
                    观察于 {formatTime(content.latest_observation.observed_at)}
                  </p>
                  <p className="text-muted-foreground mt-1 text-xs">
                    <TimelineBasis content={content} />
                  </p>
                  <p className="mt-3">
                    <PrimaryMetrics
                      metrics={content.latest_observation.metrics}
                    />
                  </p>
                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                    <span className="text-muted-foreground text-xs">
                      {content.discovery_count} 条发现依据
                    </span>
                    <Button asChild variant="secondary" size="sm">
                      <Link href={`/content/${content.id}`}>
                        查看详情
                        <ArrowRightIcon data-icon="inline-end" />
                      </Link>
                    </Button>
                  </div>
                  <OriginalContentLink
                    canonicalUrl={content.latest_observation.canonical_url}
                  />
                </article>
              ))}
            </div>

            {state.nextCursor ? (
              <div className="mt-8 flex justify-center">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => void loadMore()}
                  disabled={isLoadingMore}
                >
                  {isLoadingMore ? "正在加载" : "加载更多"}
                </Button>
              </div>
            ) : null}
            {loadMoreError ? (
              <p
                role="alert"
                className="text-destructive mt-3 text-center text-sm"
              >
                {loadMoreError}
              </p>
            ) : null}
          </>
        ) : null}
      </main>
    </div>
  );
}
