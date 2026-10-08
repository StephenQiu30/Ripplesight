"use client";
import * as UI from "@/components/ui/content";

import { toast } from "sonner";

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
  contentSourceLabel,
  contentScopeNotice,
  formatTime,
  visibilityStatusLabel,
  visibilityStatusNotice,
} from "@/app/content/components/content-presenters";
import { WebPageCaptureForm } from "@/app/content/components/webpage-capture-form";
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
import { PageState } from "@/components/system/page-state";
import { ApiRequestError } from "@/request";

type ContentListState =
  | { status: "loading" }
  | {
      status: "ready";
      items: HotKeyAPI.ContentRecordSummaryView[];
      nextCursor: string | null;
    }
  | {
      status: "error";
      message: string;
      requestId?: string;
      httpStatus?: number;
      errorCode?: string;
    };

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
    <UI.Text as="span">
      {label}：{formatTime(content.timeline_at ?? null)}
    </UI.Text>
  );
}

function toErrorState(
  error: unknown,
): Extract<ContentListState, { status: "error" }> {
  return error instanceof ApiRequestError
    ? {
        status: "error",
        message: error.message,
        requestId: error.requestId,
        httpStatus: error.status,
        errorCode: error.code,
      }
    : { status: "error", message: "作品资料加载失败，请稍后重试。" };
}

export function ContentList() {
  const [state, setState] = useState<ContentListState>({ status: "loading" });
  const [options, setOptions] = useState<FilterOptions>({ status: "loading" });
  const [draft, setDraft] = useState<ContentFilters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<ContentFilters>(EMPTY_FILTERS);
  const [filterOpen, setFilterOpen] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
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
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (!controller.signal.aborted) {
          toast.error(
            error instanceof ApiRequestError
              ? error.message
              : "来源和主题暂时无法加载，日期筛选仍可使用。",
          );
          setOptions({ status: "error" });
        }
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
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (!controller.signal.aborted) {
          const failure = toErrorState(error);
          toast.error(failure.message, {
            description: failure.requestId
              ? `请求编号：${failure.requestId}`
              : undefined,
          });
          setState(failure);
        }
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
    void load(filters);
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      contentListParams(draft);
      setApplied(draft);
      setFilterOpen(false);
      reload(draft);
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      toast.error(error instanceof Error ? error.message : "筛选条件无效。");
    }
  }

  async function loadMore() {
    if (state.status !== "ready" || !state.nextCursor || loadingMore.current)
      return;
    const controller = dataRequest.current;
    if (!controller || controller.signal.aborted) return;
    loadingMore.current = true;
    setIsLoadingMore(true);
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
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (!controller.signal.aborted) {
        if (
          error instanceof ApiRequestError &&
          (error.status === 401 || error.status === 403)
        )
          setState(toErrorState(error));
        toast.error(
          error instanceof ApiRequestError
            ? error.message
            : "后续作品加载失败，请重试。",
        );
      }
    } finally {
      if (!controller.signal.aborted) {
        loadingMore.current = false;
        setIsLoadingMore(false);
      }
    }
  }

  const filtered = Object.values(applied).some(Boolean);
  return (
    <UI.Content>
      <UI.Content className="flex flex-wrap items-end justify-between gap-6">
        <UI.Content className="flex max-w-xl flex-col gap-4">
          <UI.Heading
            level={1}
            className="text-3xl font-normal tracking-tight sm:text-4xl"
          >
            作品资料
          </UI.Heading>
          <UI.Text className="text-muted-foreground leading-7">
            阅读已保存的内容，查看评论与主题分析。
          </UI.Text>
        </UI.Content>
        <UI.Content className="flex flex-wrap gap-3">
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
              <UI.Form onSubmit={applyFilters} aria-label="筛选作品资料">
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
                    <FieldDescription>
                      <Button
                        type="button"
                        variant="link"
                        onClick={() => void loadOptions()}
                      >
                        重试加载筛选项
                      </Button>
                    </FieldDescription>
                  ) : null}
                  <UI.Content className="flex flex-wrap gap-3">
                    <Button type="submit">应用筛选</Button>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => {
                        setDraft(EMPTY_FILTERS);
                        setApplied(EMPTY_FILTERS);
                        setFilterOpen(false);
                        reload(EMPTY_FILTERS);
                      }}
                    >
                      清除筛选
                    </Button>
                  </UI.Content>
                </FieldGroup>
              </UI.Form>
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
        </UI.Content>
      </UI.Content>
      {state.status === "loading" ? (
        <PageState
          headingLevel={2}
          state="loading"
          title="正在读取作品资料"
          description="正在读取当前筛选下的作品。"
        />
      ) : null}
      {state.status === "error" ? (
        <PageState
          headingLevel={2}
          state={
            state.httpStatus === 401 || state.httpStatus === 403
              ? "forbidden"
              : "error"
          }
          title={
            state.httpStatus === 401 || state.httpStatus === 403
              ? "暂时无法访问作品资料"
              : "暂时无法读取作品"
          }
          description="请重新读取；权限变化时已清除先前列表。"
          errorCode={state.errorCode}
          httpStatus={state.httpStatus}
          action={
            <Button variant="outline" onClick={() => reload(applied)}>
              <RotateCcwIcon data-icon="inline-start" />
              重新加载
            </Button>
          }
        />
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
          <UI.Content
            as="section"
            aria-label="作品列表"
            className="mt-12 flex flex-col gap-10"
          >
            {state.items.map((content) => {
              const version = content.latest_observation.content_version;
              const title =
                version?.title || version?.body || content.external_id;
              const source = contentSourceLabel(
                content.source_key,
                content.source_name ??
                  (options.status === "ready"
                    ? options.sources.find(
                        (item) => item.source_key === content.source_key,
                      )?.display_name
                    : null),
              );
              const notice = version
                ? contentScopeNotice(version.text_scope, version.text_origin)
                : "未取得正文";
              return (
                <UI.Content
                  as="article"
                  key={content.id}
                  className="flex flex-col gap-4 sm:flex-row sm:justify-between sm:gap-8"
                >
                  <UI.Content className="flex min-w-0 flex-col gap-3">
                    <UI.Content className="text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                      <UI.Text as="span">{source}</UI.Text>
                      <TimelineBasis content={content} />
                      <ContentAnalysisStatus content={content} />
                    </UI.Content>
                    <UI.Heading
                      level={2}
                      className="line-clamp-2 text-xl leading-8 font-medium break-words"
                    >
                      <Link href={`/content/${content.id}`}>{title}</Link>
                    </UI.Heading>
                    {version?.title && version.body ? (
                      <UI.Text className="text-muted-foreground line-clamp-2 max-w-2xl text-sm leading-6 break-words">
                        {version.body}
                      </UI.Text>
                    ) : null}
                    <UI.Content className="flex flex-wrap items-center gap-3">
                      {version ? (
                        <Badge variant="secondary">
                          {contentScopeLabel(
                            version.text_scope,
                            version.text_origin,
                          )}
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
                    </UI.Content>
                    {notice ? (
                      <UI.Text className="text-muted-foreground text-xs leading-5">
                        {notice}
                      </UI.Text>
                    ) : null}
                    {content.current_visibility &&
                    content.current_visibility.status !== "visible" ? (
                      <UI.Text className="text-muted-foreground text-xs leading-5">
                        {visibilityStatusNotice(
                          content.current_visibility.status,
                        )}
                      </UI.Text>
                    ) : null}
                  </UI.Content>
                  <Button asChild variant="ghost" className="self-start">
                    <Link href={`/content/${content.id}`}>
                      查看详情
                      <ArrowRightIcon data-icon="inline-end" />
                    </Link>
                  </Button>
                </UI.Content>
              );
            })}
          </UI.Content>
          {state.nextCursor ? (
            <UI.Content className="mt-12 flex justify-center">
              <Button
                variant="outline"
                onClick={() => void loadMore()}
                disabled={isLoadingMore}
              >
                {isLoadingMore ? "正在加载" : "加载更多"}
              </Button>
            </UI.Content>
          ) : null}
        </>
      ) : null}
    </UI.Content>
  );
}
