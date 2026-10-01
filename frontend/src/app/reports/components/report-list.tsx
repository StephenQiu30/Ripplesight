"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, ChevronDownIcon, RotateCcwIcon } from "lucide-react";
import { listMonitorTopics } from "@/api/jiankongzhuti";
import { listReports } from "@/api/ribao";
import { WorkspaceHeader } from "@/components/navigation/workspace-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/request";

type ListState =
  | { status: "loading" }
  | {
      status: "ready";
      items: HotKeyAPI.ReportSummaryView[];
      nextCursor: string | null;
    }
  | { status: "error"; message: string };

function errorMessage(error: unknown): string {
  return error instanceof ApiRequestError
    ? `${error.message}${error.requestId ? ` 请求编号：${error.requestId}` : ""}`
    : "报告加载失败，请稍后重试。";
}

function reportDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(value));
}

export function ReportList() {
  const [topics, setTopics] = useState<HotKeyAPI.MonitorTopicView[]>([]);
  const [topicOptionsError, setTopicOptionsError] = useState(false);
  const [topicId, setTopicId] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [reloadToken, setReloadToken] = useState(0);
  const rangeError =
    dateFrom && dateTo && dateFrom > dateTo
      ? "开始日期不能晚于结束日期。"
      : null;

  useEffect(() => {
    const current = new AbortController();
    void (async () => {
      const all: HotKeyAPI.MonitorTopicView[] = [];
      let cursor: string | null = null;
      do {
        const page: HotKeyAPI.PageViewMonitorTopicView_ =
          await listMonitorTopics(
            {
              limit: 50,
              include_archived: true,
              ...(cursor ? { cursor } : {}),
            },
            { signal: current.signal },
          );
        all.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor && !current.signal.aborted);
      if (!current.signal.aborted) {
        setTopics(all);
        setTopicOptionsError(false);
      }
    })().catch(() => {
      if (!current.signal.aborted) setTopicOptionsError(true);
    });
    return () => current.abort();
  }, [reloadToken]);

  return (
    <div className="bg-background min-h-screen">
      <WorkspaceHeader current="reports" />
      <main className="mx-auto max-w-6xl px-5 py-12 sm:px-8 sm:py-16">
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
              已有报告
            </h1>
            <p className="text-muted-foreground mt-4 leading-7">
              按主题和日期，阅读已经定稿的日报。
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => setReloadToken((value) => value + 1)}
          >
            <RotateCcwIcon data-icon="inline-start" />
            刷新
          </Button>
        </div>
        <Collapsible className="mt-8">
          <CollapsibleTrigger asChild>
            <Button variant="ghost">
              筛选报告
              <ChevronDownIcon data-icon="inline-end" />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-5 flex flex-col gap-4">
            <div className="grid gap-5 sm:grid-cols-3">
              <Field>
                <FieldLabel htmlFor="report-topic">关注主题</FieldLabel>
                <Select value={topicId} onValueChange={setTopicId}>
                  <SelectTrigger id="report-topic" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="all">全部主题</SelectItem>
                      {topics.map((topic) => (
                        <SelectItem key={topic.id} value={topic.id}>
                          {topic.name}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="report-date-from">开始日期</FieldLabel>
                <Input
                  id="report-date-from"
                  type="date"
                  value={dateFrom}
                  onChange={(event) => setDateFrom(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="report-date-to">结束日期</FieldLabel>
                <Input
                  id="report-date-to"
                  type="date"
                  value={dateTo}
                  onChange={(event) => setDateTo(event.target.value)}
                />
              </Field>
            </div>
            {topicOptionsError ? (
              <p className="text-muted-foreground text-sm">
                主题选项暂时无法读取，仍可按日期查看报告。
              </p>
            ) : null}
          </CollapsibleContent>
        </Collapsible>
        {rangeError ? (
          <Alert variant="destructive" className="mt-6">
            <AlertDescription>{rangeError}</AlertDescription>
          </Alert>
        ) : null}
        {!rangeError ? (
          <ReportResults
            key={`${topicId}|${dateFrom}|${dateTo}|${reloadToken}`}
            topicId={topicId}
            dateFrom={dateFrom}
            dateTo={dateTo}
            onRetry={() => setReloadToken((value) => value + 1)}
          />
        ) : null}
      </main>
    </div>
  );
}

function ReportResults({
  topicId,
  dateFrom,
  dateTo,
  onRetry,
}: {
  topicId: string;
  dateFrom: string;
  dateTo: string;
  onRetry: () => void;
}) {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const paginationLock = useRef(false);
  useEffect(() => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    void listReports(
      {
        kind: "daily",
        topic_id: topicId === "all" ? undefined : topicId,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit: 20,
      },
      { signal: current.signal },
    )
      .then((page) => {
        if (!current.signal.aborted)
          setState({
            status: "ready",
            items: page.items,
            nextCursor: page.next_cursor,
          });
      })
      .catch((error: unknown) => {
        if (!current.signal.aborted)
          setState({ status: "error", message: errorMessage(error) });
      });
    return () => current.abort();
  }, [topicId, dateFrom, dateTo]);

  async function loadMore() {
    const current = controller.current;
    if (
      state.status !== "ready" ||
      !state.nextCursor ||
      !current ||
      current.signal.aborted ||
      paginationLock.current
    )
      return;
    paginationLock.current = true;
    setLoadingMore(true);
    setPageError(null);
    try {
      const page = await listReports(
        {
          kind: "daily",
          topic_id: topicId === "all" ? undefined : topicId,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          cursor: state.nextCursor,
          limit: 20,
        },
        { signal: current.signal },
      );
      if (!current.signal.aborted)
        setState({
          ...state,
          items: [...state.items, ...page.items],
          nextCursor: page.next_cursor,
        });
    } catch (error) {
      if (!current.signal.aborted) setPageError(errorMessage(error));
    } finally {
      if (!current.signal.aborted) {
        paginationLock.current = false;
        setLoadingMore(false);
      }
    }
  }

  return (
    <>
      {state.status === "loading" ? (
        <div aria-label="正在读取报告" className="mt-10 flex flex-col gap-4">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : null}
      {state.status === "error" ? (
        <Alert variant="destructive" className="mt-10">
          <AlertTitle>暂时无法读取报告</AlertTitle>
          <AlertDescription>
            <p>{state.message}</p>
            <Button variant="outline" className="mt-4" onClick={onRetry}>
              重新加载
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}
      {state.status === "ready" ? (
        <section aria-label="报告列表" className="mt-10">
          {!state.items.length ? (
            <Empty className="py-16">
              <EmptyHeader>
                <EmptyTitle>暂无已定稿报告</EmptyTitle>
                <EmptyDescription>
                  已有日报会显示在这里，也可以调整筛选条件。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ItemGroup>
              {state.items.map((report) => (
                <Item key={report.id} role="listitem" className="py-6">
                  <ItemContent>
                    <ItemTitle>
                      {reportDate(report.window_start)} · {report.topic_name}
                    </ItemTitle>
                    <ItemDescription className="flex items-center gap-3">
                      <Badge variant="secondary">
                        {report.generator === "model" ? "模型版" : "模板版"}
                      </Badge>
                      第 {report.version} 版
                    </ItemDescription>
                  </ItemContent>
                  <ItemActions>
                    <Button asChild variant="ghost">
                      <Link href={`/reports/${report.id}`}>
                        查看报告
                        <ArrowRightIcon data-icon="inline-end" />
                      </Link>
                    </Button>
                  </ItemActions>
                </Item>
              ))}
            </ItemGroup>
          )}
          {pageError ? (
            <Alert variant="destructive" className="mt-6">
              <AlertDescription>{pageError}</AlertDescription>
            </Alert>
          ) : null}
          {state.nextCursor ? (
            <Button
              variant="outline"
              className="mt-6"
              disabled={loadingMore}
              onClick={() => void loadMore()}
            >
              {loadingMore
                ? "正在加载"
                : pageError
                  ? "重试加载更多"
                  : "加载更多"}
            </Button>
          ) : null}
        </section>
      ) : null}
    </>
  );
}
