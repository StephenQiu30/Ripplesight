"use client";
import * as UI from "@/components/ui/content";

import { toast } from "sonner";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, ChevronDownIcon, RotateCcwIcon } from "lucide-react";
import { listMonitorTopics } from "@/api/jiankongzhuti";
import { listReports } from "@/api/ribao";
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
  SelectLabel,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { PageState } from "@/components/system/page-state";
import { ApiRequestError } from "@/request";

type ListState =
  | { status: "loading" }
  | {
      status: "ready";
      items: HotKeyAPI.ReportSummaryView[];
      nextCursor: string | null;
    }
  | {
      status: "error";
      message: string;
      httpStatus?: number;
      errorCode?: string;
    };

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
  const searchParams = useSearchParams();
  const kind = searchParams.get("kind") === "weekly" ? "weekly" : "daily";
  const topicId = searchParams.get("topic_id") || "all";
  const validDate = (value: string | null) =>
    value &&
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value
      ? value
      : "";
  const dateFrom = validDate(searchParams.get("date_from"));
  const dateTo = validDate(searchParams.get("date_to"));
  const navigate = (key: string, value: string) => {
    const query = new URLSearchParams(window.location.search);
    if (!value || value === "all") query.delete(key);
    else query.set(key, value);
    query.delete("cursor");
    window.history.replaceState(
      null,
      "",
      query.size ? `/reports?${query}` : "/reports",
    );
  };
  const [reloadToken, setReloadToken] = useState(0);

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
    })().catch((error: unknown) => {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (!current.signal.aborted) {
        toast.error(
          error instanceof ApiRequestError
            ? error.message
            : "主题选项暂时无法读取。",
        );
        setTopicOptionsError(true);
      }
    });
    return () => current.abort();
  }, [reloadToken]);

  return (
    <UI.Content>
      <UI.Content className="flex flex-wrap items-end justify-between gap-5">
        <UI.Content>
          <UI.Heading
            level={1}
            className="text-3xl font-medium tracking-tight sm:text-4xl"
          >
            已有报告
          </UI.Heading>
          <UI.Text className="text-muted-foreground mt-4 leading-7">
            按主题和日期，阅读已经定稿的日报和周报。
          </UI.Text>
        </UI.Content>
        <Button
          variant="outline"
          onClick={() => setReloadToken((value) => value + 1)}
        >
          <RotateCcwIcon data-icon="inline-start" />
          刷新
        </Button>
      </UI.Content>
      <ToggleGroup
        type="single"
        value={kind}
        onValueChange={(value) => {
          if (value === "daily" || value === "weekly") navigate("kind", value);
        }}
        aria-label="报告周期"
        variant="outline"
        className="mt-8"
      >
        <ToggleGroupItem value="daily">日报</ToggleGroupItem>
        <ToggleGroupItem value="weekly">周报</ToggleGroupItem>
      </ToggleGroup>
      <Collapsible className="mt-5">
        <CollapsibleTrigger asChild>
          <Button variant="ghost">
            筛选报告
            <ChevronDownIcon data-icon="inline-end" />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-5 flex flex-col gap-4">
          <UI.Content className="grid gap-5 sm:grid-cols-3">
            <Field>
              <FieldLabel htmlFor="report-topic">关注主题</FieldLabel>
              <Select
                value={topicId}
                onValueChange={(value) => navigate("topic_id", value)}
              >
                <SelectTrigger id="report-topic" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectLabel className="sr-only">关注主题</SelectLabel>
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
                onChange={(event) => {
                  const next = event.target.value;
                  const upper = validDate(
                    new URLSearchParams(window.location.search).get("date_to"),
                  );
                  if (next && upper && next > upper) {
                    toast.error("开始日期不能晚于结束日期。");
                    return;
                  }
                  navigate("date_from", next);
                }}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="report-date-to">结束日期</FieldLabel>
              <Input
                id="report-date-to"
                type="date"
                value={dateTo}
                onChange={(event) => {
                  const next = event.target.value;
                  const lower = validDate(
                    new URLSearchParams(window.location.search).get(
                      "date_from",
                    ),
                  );
                  if (next && lower && lower > next) {
                    toast.error("开始日期不能晚于结束日期。");
                    return;
                  }
                  navigate("date_to", next);
                }}
              />
            </Field>
          </UI.Content>
          {topicOptionsError ? (
            <UI.Text className="text-muted-foreground text-sm">
              主题选项暂时无法读取，仍可按日期查看报告。
            </UI.Text>
          ) : null}
        </CollapsibleContent>
      </Collapsible>
      <ReportResults
        key={`${kind}|${topicId}|${dateFrom}|${dateTo}|${reloadToken}`}
        kind={kind}
        topicId={topicId}
        dateFrom={dateFrom}
        dateTo={dateTo}
        onRetry={() => setReloadToken((value) => value + 1)}
      />
    </UI.Content>
  );
}

function ReportResults({
  kind,
  topicId,
  dateFrom,
  dateTo,
  onRetry,
}: {
  kind: "daily" | "weekly";
  topicId: string;
  dateFrom: string;
  dateTo: string;
  onRetry: () => void;
}) {
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const paginationLock = useRef(false);
  useEffect(() => {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    void listReports(
      {
        kind,
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
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (!current.signal.aborted) {
          toast.error(errorMessage(error));
          setState({
            status: "error",
            message: errorMessage(error),
            httpStatus:
              error instanceof ApiRequestError ? error.status : undefined,
            errorCode:
              error instanceof ApiRequestError ? error.code : undefined,
          });
        }
      });
    return () => current.abort();
  }, [kind, topicId, dateFrom, dateTo]);

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
    try {
      const page = await listReports(
        {
          kind,
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
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (!current.signal.aborted) {
        if (
          error instanceof ApiRequestError &&
          (error.status === 401 || error.status === 403)
        )
          setState({
            status: "error",
            message: errorMessage(error),
            httpStatus: error.status,
            errorCode: error.code,
          });
        toast.error(errorMessage(error));
      }
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
        <PageState
          headingLevel={2}
          state="loading"
          title="正在读取报告"
          description="正在读取当前筛选下的报告。"
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
              ? "暂时无法访问报告"
              : "暂时无法读取报告"
          }
          description="请重新读取；权限变化时已清除先前列表。"
          errorCode={state.errorCode}
          httpStatus={state.httpStatus}
          action={
            <Button variant="outline" onClick={onRetry}>
              重新加载
            </Button>
          }
        />
      ) : null}
      {state.status === "ready" ? (
        <UI.Content as="section" aria-label="报告列表" className="mt-10">
          {!state.items.length ? (
            <Empty className="py-16">
              <EmptyHeader>
                <EmptyTitle>暂无已定稿报告</EmptyTitle>
                <EmptyDescription>
                  已有日报和周报会显示在这里，也可以调整筛选条件。
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
          {state.nextCursor ? (
            <Button
              variant="outline"
              className="mt-6"
              disabled={loadingMore}
              onClick={() => void loadMore()}
            >
              {loadingMore ? "正在加载" : "加载更多"}
            </Button>
          ) : null}
        </UI.Content>
      ) : null}
    </>
  );
}
