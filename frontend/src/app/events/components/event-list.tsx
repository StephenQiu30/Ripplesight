"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { listEvents } from "@/api/shijian";
import { EventHotList } from "./event-hot-list";
import { listMonitorTopics } from "@/api/jiankongzhuti";
import { listSourceCapabilities } from "@/api/laiyuannengli";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { FieldGroup, Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/request";

type ResultState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; page: HotKeyAPI.PageViewEventReadView_ };

function message(error: unknown): string {
  return error instanceof ApiRequestError
    ? `${error.message}${error.requestId ? ` 请求编号：${error.requestId}` : ""}`
    : "事件读取失败，请稍后重试。";
}

export function EventList() {
  const [query, setQuery] = useState("");
  const [topicId, setTopicId] = useState("all");
  const [sourceKey, setSourceKey] = useState("all");
  const [params, setParams] = useState<HotKeyAPI.listEventsParams>({
    limit: 20,
  });
  const [refresh, setRefresh] = useState(0);
  const [topics, setTopics] = useState<HotKeyAPI.MonitorTopicView[]>([]);
  const [sources, setSources] = useState<HotKeyAPI.SourcePlatformView[]>([]);
  const [optionsError, setOptionsError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      listSourceCapabilities({ signal: controller.signal }),
      (async () => {
        const items: HotKeyAPI.MonitorTopicView[] = [];
        let cursor: string | null = null;
        do {
          const page: HotKeyAPI.PageViewMonitorTopicView_ =
            await listMonitorTopics(
              {
                limit: 50,
                include_archived: true,
                ...(cursor ? { cursor } : {}),
              },
              { signal: controller.signal },
            );
          items.push(...page.items);
          cursor = page.next_cursor;
        } while (cursor && !controller.signal.aborted);
        return items;
      })(),
    ])
      .then(([sourcePage, topicItems]) => {
        if (!controller.signal.aborted) {
          setSources(sourcePage.items);
          setTopics(topicItems);
          setOptionsError(false);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setOptionsError(true);
      });
    return () => controller.abort();
  }, [refresh]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setParams({
      limit: 20,
      ...(query.trim() ? { query: query.trim() } : {}),
      ...(topicId !== "all" ? { topic_id: topicId } : {}),
      ...(sourceKey !== "all" ? { source_key: sourceKey } : {}),
    });
    setRefresh((value) => value + 1);
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
            已确认事件
          </h1>
          <p className="text-muted-foreground mt-4 leading-7">
            阅读已归并的事件与对应的固定版本证据。
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => setRefresh((value) => value + 1)}
        >
          刷新事件
        </Button>
      </div>
      <form onSubmit={applyFilters}>
        <FieldGroup className="mt-8 grid items-end gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Field>
            <FieldLabel htmlFor="event-query">搜索事件</FieldLabel>
            <Input
              id="event-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              maxLength={200}
              placeholder="标题或证据正文"
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="event-topic">关注主题</FieldLabel>
            <Select value={topicId} onValueChange={setTopicId}>
              <SelectTrigger id="event-topic" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部关注</SelectItem>
                {topics.map((topic) => (
                  <SelectItem key={topic.id} value={topic.id}>
                    {topic.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="event-source">证据来源</FieldLabel>
            <Select value={sourceKey} onValueChange={setSourceKey}>
              <SelectTrigger id="event-source" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部来源</SelectItem>
                {sources.map((source) => (
                  <SelectItem key={source.source_key} value={source.source_key}>
                    {source.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Button type="submit">应用筛选</Button>
        </FieldGroup>
      </form>
      <EventHotList topicId={params.topic_id ?? undefined} />
      {optionsError ? (
        <p role="status" className="text-muted-foreground mt-4 text-sm">
          筛选选项暂时不可用，仍可搜索事件。刷新可重试。
        </p>
      ) : null}
      <EventResults
        key={`${JSON.stringify(params)}:${refresh}`}
        params={params}
        sources={sources}
      />
    </div>
  );
}

function EventResults({
  params,
  sources,
}: {
  params: HotKeyAPI.listEventsParams;
  sources: HotKeyAPI.SourcePlatformView[];
}) {
  const [state, setState] = useState<ResultState>({ status: "loading" });
  const [retry, setRetry] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    void listEvents(params, { signal: current.signal })
      .then((page) => {
        if (!current.signal.aborted) setState({ status: "ready", page });
      })
      .catch((error: unknown) => {
        if (!current.signal.aborted)
          setState({ status: "error", message: message(error) });
      });
    return () => current.abort();
  }, [params, retry]);

  async function loadMore() {
    if (state.status !== "ready" || !state.page.next_cursor || loadingMore)
      return;
    setLoadingMore(true);
    setPageError(null);
    const signal = controller.current?.signal;
    try {
      const page = await listEvents(
        { ...params, cursor: state.page.next_cursor },
        { signal },
      );
      if (!signal?.aborted) {
        setState({
          status: "ready",
          page: {
            items: [
              ...new Map(
                [...state.page.items, ...page.items].map((item) => [
                  item.id,
                  item,
                ]),
              ).values(),
            ],
            next_cursor: page.next_cursor,
          },
        });
      }
    } catch (error: unknown) {
      if (!signal?.aborted) setPageError(message(error));
    } finally {
      if (!signal?.aborted) setLoadingMore(false);
    }
  }

  if (state.status === "loading")
    return (
      <div aria-label="正在读取事件" className="mt-10 flex flex-col gap-y-5">
        {[1, 2, 3].map((id) => (
          <Skeleton key={id} className="h-28 w-full" />
        ))}
      </div>
    );
  if (state.status === "error")
    return (
      <Alert variant="destructive" className="mt-10">
        <AlertTitle>无法读取事件</AlertTitle>
        <AlertDescription>
          {state.message}
          <Button
            variant="outline"
            onClick={() => {
              setState({ status: "loading" });
              setRetry((value) => value + 1);
            }}
          >
            重试事件读取
          </Button>
        </AlertDescription>
      </Alert>
    );

  const names = new Map(
    sources.map((source) => [source.source_key, source.display_name]),
  );
  return (
    <section
      aria-label="已确认事件列表"
      className="mt-10 flex flex-col gap-y-8"
    >
      {!state.page.items.length ? (
        <Empty className="py-12">
          <EmptyHeader>
            <EmptyTitle>暂无已确认事件</EmptyTitle>
            <EmptyDescription>
              当前筛选下还没有具有可读成员的已确认事件。可以先查看相关内容。
            </EmptyDescription>
            <Button asChild variant="outline">
              <Link href="/content">查看相关内容</Link>
            </Button>
          </EmptyHeader>
        </Empty>
      ) : (
        state.page.items.map((item) => (
          <article key={item.id} className="bg-muted/30 rounded-xl p-6">
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant="secondary">
                {item.evidence_state === "partial" ? "部分证据可读" : "已确认"}
              </Badge>
              <span className="text-muted-foreground text-sm">
                {item.readable_member_count} / {item.member_count} 条成员可读
              </span>
            </div>
            <h2 className="mt-4 text-xl font-medium">
              <Link
                className="underline-offset-4 hover:underline"
                href={`/events/${item.id}`}
              >
                {item.title ?? "证据暂不可读的事件"}
              </Link>
            </h2>
            {item.summary ? (
              <p className="text-muted-foreground mt-3 leading-7">
                {item.summary}
              </p>
            ) : (
              <p className="text-muted-foreground mt-3 text-sm">
                派生标题和摘要暂不可读，可进入事件查看仍可读的成员。
              </p>
            )}
            <p className="text-muted-foreground mt-5 text-sm">
              {Object.entries(item.source_counts)
                .map(
                  ([source, count]) =>
                    `${names.get(source) ?? source} ${count} 条`,
                )
                .join(" · ")}
            </p>
            <p className="text-muted-foreground mt-2 text-sm">
              首次{item.first_seen_basis === "published" ? "发布" : "发现"}：
              {new Date(item.first_seen_at).toLocaleString("zh-CN")}
            </p>
          </article>
        ))
      )}
      {pageError ? (
        <Alert variant="destructive">
          <AlertDescription>{pageError}</AlertDescription>
        </Alert>
      ) : null}
      {state.page.next_cursor ? (
        <Button
          variant="outline"
          disabled={loadingMore}
          onClick={() => void loadMore()}
        >
          {loadingMore ? "正在读取更多事件…" : "加载更多事件"}
        </Button>
      ) : null}
    </section>
  );
}
