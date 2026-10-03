"use client";

import Link from "next/link";
import {
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  ArrowRightIcon,
  FilterIcon,
  PlusIcon,
  RotateCcwIcon,
} from "lucide-react";
import { listContentRecords } from "@/api/zuopinziliao";
import { listMonitorTopics } from "@/api/jiankongzhuti";
import { listSourceCapabilities } from "@/api/laiyuannengli";
import {
  contentScopeLabel,
  contentScopeNotice,
  formatTime,
  visibilityStatusLabel,
  visibilityStatusNotice,
} from "@/app/content/components/content-presenters";
import { WebPageCaptureForm } from "@/app/content/components/webpage-capture-form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
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
import { Input } from "@/components/ui/input";
import {
  SelectLabel,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
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
  query?: string;
  sourceKey: string;
  topicId: string;
  startDate: string;
  endDate: string;
  analysisState: AnalysisFilter;
};

const EMPTY_FILTERS: ContentFilters = {
  query: "",
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

async function fetchFilterOptions(
  signal?: AbortSignal,
): Promise<Extract<FilterOptions, { status: "ready" }>> {
  const [sourcePage, topics] = await Promise.all([
    listSourceCapabilities({ signal }),
    (async () => {
      const all: HotKeyAPI.MonitorTopicView[] = [];
      let cursor: string | null = null;
      do {
        const page = await listMonitorTopics(
          {
            include_archived: true,
            limit: 50,
            ...(cursor ? { cursor } : {}),
          },
          { signal },
        );
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
  const rawQuery = filters.query ?? "";
  const query = rawQuery.trim();
  if (
    rawQuery.length > 200 ||
    rawQuery.includes("\u0000") ||
    new Set(query.toLowerCase().split(/\s+/).filter(Boolean)).size > 6
  ) {
    throw new Error("搜索最多 200 字符、6 个不同词，多个词以空格分隔。");
  }
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
    ...(query ? { q: query } : {}),
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

function toErrorState(
  error: unknown,
): Extract<ContentListState, { status: "error" }> {
  return error instanceof ApiRequestError
    ? { status: "error", message: error.message, requestId: error.requestId }
    : { status: "error", message: "作品资料加载失败，请稍后重试。" };
}

export function ContentList() {
  const [state, setState] = useState<ContentListState>({ status: "loading" });
  const [options, setOptions] = useState<FilterOptions>({ status: "loading" });
  const [draft, setDraft] = useState<ContentFilters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<ContentFilters>(EMPTY_FILTERS);
  const [filterOpen, setFilterOpen] = useState(false);
  const [filterError, setFilterError] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const dataRequest = useRef<AbortController | null>(null);
  const optionRequest = useRef<AbortController | null>(null);
  const loadingMore = useRef(false);

  const loadOptions = useCallback(() => {
    optionRequest.current?.abort();
    const controller = new AbortController();
    optionRequest.current = controller;
    return fetchFilterOptions(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setOptions(result);
      })
      .catch(() => {
        if (!controller.signal.aborted) setOptions({ status: "error" });
      });
  }, []);

  const load = useCallback((filters: ContentFilters) => {
    dataRequest.current?.abort();
    const controller = new AbortController();
    dataRequest.current = controller;
    return listContentRecords(contentListParams(filters), {
      signal: controller.signal,
    })
      .then((page) => {
        if (!controller.signal.aborted)
          setState({
            status: "ready",
            items: page.items,
            nextCursor: page.next_cursor,
          });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState(toErrorState(error));
      });
  }, []);

  useEffect(() => {
    void load(EMPTY_FILTERS);
    void loadOptions();
    return () => {
      dataRequest.current?.abort();
      optionRequest.current?.abort();
    };
  }, [load, loadOptions]);

  function reload(filters: ContentFilters) {
    loadingMore.current = false;
    setState({ status: "loading" });
    setIsLoadingMore(false);
    setLoadMoreError(null);
    void load(filters);
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      contentListParams(draft);
      setFilterError(null);
      setApplied(draft);
      setFilterOpen(false);
      reload(draft);
    } catch (error) {
      setFilterError(error instanceof Error ? error.message : "筛选条件无效。");
    }
  }

  async function loadMore() {
    if (state.status !== "ready" || !state.nextCursor || loadingMore.current)
      return;
    const controller = dataRequest.current;
    if (!controller || controller.signal.aborted) return;
    loadingMore.current = true;
    setIsLoadingMore(true);
    setLoadMoreError(null);
    try {
      const page = await listContentRecords(
        contentListParams(applied, state.nextCursor),
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
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
      if (!controller.signal.aborted)
        setLoadMoreError(
          error instanceof ApiRequestError
            ? error.message
            : "后续作品加载失败，请重试。",
        );
    } finally {
      if (!controller.signal.aborted) {
        loadingMore.current = false;
        setIsLoadingMore(false);
      }
    }
  }

  const filtered = Object.values(applied).some(Boolean);
  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="flex max-w-xl flex-col gap-4">
          <h1 className="text-3xl font-normal tracking-tight sm:text-4xl">
            作品资料
          </h1>
          <p className="text-muted-foreground leading-7">
            阅读已保存的内容，查看评论与主题分析。
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Dialog open={filterOpen} onOpenChange={setFilterOpen}>
            <DialogTrigger asChild>
              <Button variant="outline">
                <FilterIcon data-icon="inline-start" />
                筛选{filtered ? " · 已应用" : ""}
              </Button>
            </DialogTrigger>
            <DialogContent className="max-h-svh overflow-y-auto sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>筛选作品资料</DialogTitle>
                <DialogDescription>
                  日期按北京时间，结束日期包含当日。日期范围最多 31 天。
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={applyFilters} aria-label="筛选作品资料">
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="content-query">正文搜索</FieldLabel>
                    <Input
                      id="content-query"
                      value={draft.query ?? ""}
                      maxLength={200}
                      placeholder="例如 OpenAI 模型"
                      onChange={(event) =>
                        setDraft({ ...draft, query: event.target.value })
                      }
                    />
                    <FieldDescription>
                      搜索已保存的标题和正文。最多 6
                      个不同词，多个词以空格分隔并同时命中。
                    </FieldDescription>
                  </Field>
                  <Field data-disabled={options.status !== "ready"}>
                    <FieldLabel htmlFor="content-source">来源</FieldLabel>
                    <Select
                      value={draft.sourceKey || "all"}
                      onValueChange={(value) =>
                        setDraft({
                          ...draft,
                          sourceKey: value === "all" ? "" : value,
                        })
                      }
                      disabled={options.status !== "ready"}
                    >
                      <SelectTrigger id="content-source" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectLabel className="sr-only">来源</SelectLabel>
                          <SelectItem value="all">全部来源</SelectItem>
                          {options.status === "ready"
                            ? options.sources.map((source) => (
                                <SelectItem
                                  key={source.source_key}
                                  value={source.source_key}
                                >
                                  {source.display_name}
                                </SelectItem>
                              ))
                            : null}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field data-disabled={options.status !== "ready"}>
                    <FieldLabel htmlFor="content-topic">主题</FieldLabel>
                    <Select
                      value={draft.topicId || "all"}
                      onValueChange={(value) =>
                        setDraft({
                          ...draft,
                          topicId: value === "all" ? "" : value,
                          analysisState: "",
                        })
                      }
                      disabled={options.status !== "ready"}
                    >
                      <SelectTrigger id="content-topic" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectLabel className="sr-only">主题</SelectLabel>
                          <SelectItem value="all">全部主题</SelectItem>
                          {options.status === "ready"
                            ? options.topics.map((topic) => (
                                <SelectItem key={topic.id} value={topic.id}>
                                  {topic.name}
                                  {topic.status === "archived"
                                    ? "（已归档）"
                                    : ""}
                                </SelectItem>
                              ))
                            : null}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="content-start-date">
                      开始日期
                    </FieldLabel>
                    <Input
                      id="content-start-date"
                      type="date"
                      value={draft.startDate}
                      onChange={(event) =>
                        setDraft({ ...draft, startDate: event.target.value })
                      }
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="content-end-date">
                      结束日期（含）
                    </FieldLabel>
                    <Input
                      id="content-end-date"
                      type="date"
                      value={draft.endDate}
                      onChange={(event) =>
                        setDraft({ ...draft, endDate: event.target.value })
                      }
                    />
                  </Field>
                  <Field data-disabled={!draft.topicId}>
                    <FieldLabel htmlFor="content-analysis-state">
                      标注状态
                    </FieldLabel>
                    <Select
                      value={draft.analysisState || "all"}
                      onValueChange={(value) =>
                        setDraft({
                          ...draft,
                          analysisState:
                            value === "all" ? "" : (value as AnalysisFilter),
                        })
                      }
                      disabled={!draft.topicId}
                    >
                      <SelectTrigger
                        id="content-analysis-state"
                        className="w-full"
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectLabel className="sr-only">
                            标注状态
                          </SelectLabel>
                          <SelectItem value="all">全部状态</SelectItem>
                          <SelectItem value="missing">暂无标注记录</SelectItem>
                          <SelectItem value="pending">等待标注</SelectItem>
                          <SelectItem value="failed">标注失败</SelectItem>
                          <SelectItem value="invalid">标注无效</SelectItem>
                          <SelectItem value="valid">已有有效结论</SelectItem>
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                    <FieldDescription>
                      选择主题后可筛选其分析状态。
                    </FieldDescription>
                  </Field>
                  {options.status === "error" ? (
                    <FieldError>
                      来源和主题暂时无法加载，日期筛选仍可使用。
                      <Button
                        type="button"
                        variant="link"
                        onClick={() => void loadOptions()}
                      >
                        重试加载筛选项
                      </Button>
                    </FieldError>
                  ) : null}
                  {filterError ? <FieldError>{filterError}</FieldError> : null}
                  <div className="flex flex-wrap gap-3">
                    <Button type="submit">应用筛选</Button>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => {
                        setDraft(EMPTY_FILTERS);
                        setApplied(EMPTY_FILTERS);
                        setFilterError(null);
                        setFilterOpen(false);
                        reload(EMPTY_FILTERS);
                      }}
                    >
                      清除筛选
                    </Button>
                  </div>
                </FieldGroup>
              </form>
            </DialogContent>
          </Dialog>
          <Dialog>
            <DialogTrigger asChild>
              <Button>
                <PlusIcon data-icon="inline-start" />
                添加网页
              </Button>
            </DialogTrigger>
            <DialogContent className="max-h-svh overflow-y-auto sm:max-w-lg">
              <DialogHeader className="sr-only">
                <DialogTitle>添加网页</DialogTitle>
                <DialogDescription>
                  提交网页地址创建采集任务。
                </DialogDescription>
              </DialogHeader>
              <WebPageCaptureForm />
            </DialogContent>
          </Dialog>
        </div>
      </div>
      {state.status === "loading" ? (
        <div
          aria-label="正在读取作品资料"
          className="mt-12 flex flex-col gap-6"
        >
          {[0, 1, 2].map((item) => (
            <Skeleton key={item} className="h-24 w-full" />
          ))}
        </div>
      ) : null}
      {state.status === "error" ? (
        <Alert variant="destructive" className="mt-12">
          <AlertTitle>暂时无法读取作品</AlertTitle>
          <AlertDescription>
            {state.message}
            {state.requestId ? ` 请求编号：${state.requestId}` : null}
            <Button variant="outline" onClick={() => reload(applied)}>
              <RotateCcwIcon data-icon="inline-start" />
              重新加载
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {state.status === "ready" && state.items.length === 0 ? (
        <Empty className="mt-12">
          <EmptyHeader>
            <EmptyTitle>当前条件下没有可读作品</EmptyTitle>
            <EmptyDescription>
              完成采集并保存后，作品会显示在这里；当前为空不代表来源返回了零结果。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : null}
      {state.status === "ready" && state.items.length > 0 ? (
        <>
          <section aria-label="作品列表" className="mt-12 flex flex-col gap-10">
            {state.items.map((content) => {
              const version = content.latest_observation.content_version;
              const title =
                version?.title || version?.body || content.external_id;
              const source =
                options.status === "ready"
                  ? (options.sources.find(
                      (item) => item.source_key === content.source_key,
                    )?.display_name ?? content.source_key)
                  : content.source_key;
              const notice = version
                ? contentScopeNotice(version.text_scope)
                : "未取得正文";
              return (
                <article
                  key={content.id}
                  className="flex flex-col gap-4 sm:flex-row sm:justify-between sm:gap-8"
                >
                  <div className="flex min-w-0 flex-col gap-3">
                    <div className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                      <span>{source}</span>
                      <TimelineBasis content={content} />
                      <ContentAnalysisStatus content={content} />
                    </div>
                    <h2 className="line-clamp-2 text-xl leading-8 font-medium break-words">
                      <Link href={`/content/${content.id}`}>{title}</Link>
                    </h2>
                    {version?.title && version.body ? (
                      <p className="text-muted-foreground line-clamp-2 max-w-2xl text-sm leading-6 break-words">
                        {version.body}
                      </p>
                    ) : null}
                    <div className="flex flex-wrap items-center gap-3">
                      {version ? (
                        <Badge variant="secondary">
                          {contentScopeLabel(version.text_scope)}
                        </Badge>
                      ) : null}
                      {content.current_visibility &&
                      content.current_visibility.status !== "visible" ? (
                        <Badge variant="outline">
                          {visibilityStatusLabel(
                            content.current_visibility.status,
                          )}
                        </Badge>
                      ) : null}
                    </div>
                    {notice ? (
                      <p className="text-muted-foreground text-xs leading-5">
                        {notice}
                      </p>
                    ) : null}
                    {content.current_visibility &&
                    content.current_visibility.status !== "visible" ? (
                      <p className="text-muted-foreground text-xs leading-5">
                        {visibilityStatusNotice(
                          content.current_visibility.status,
                        )}
                      </p>
                    ) : null}
                  </div>
                  <Button asChild variant="ghost" className="self-start">
                    <Link href={`/content/${content.id}`}>
                      查看详情
                      <ArrowRightIcon data-icon="inline-end" />
                    </Link>
                  </Button>
                </article>
              );
            })}
          </section>
          {state.nextCursor ? (
            <div className="mt-12 flex justify-center">
              <Button
                variant="outline"
                onClick={() => void loadMore()}
                disabled={isLoadingMore}
              >
                {isLoadingMore ? "正在加载" : "加载更多"}
              </Button>
            </div>
          ) : null}
          {loadMoreError ? (
            <Alert variant="destructive" className="mt-4">
              <AlertDescription>{loadMoreError}</AlertDescription>
            </Alert>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
