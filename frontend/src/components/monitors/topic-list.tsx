"use client";

import { toast } from "sonner";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, RotateCcwIcon } from "lucide-react";

import { listMonitorTopics } from "@/api/jiankongzhuti";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Field, FieldLabel } from "@/components/ui/field";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { ApiRequestError } from "@/request";

type Failure = { message: string; requestId?: string };
type TopicListState =
  | { status: "loading" }
  | {
      status: "ready";
      topics: HotKeyAPI.MonitorTopicView[];
      nextCursor: string | null;
    }
  | ({ status: "error" } & Failure);

function toFailure(error: unknown): Failure {
  return {
    message:
      error instanceof ApiRequestError
        ? error.message
        : "关注列表加载失败，请稍后重试。",
    requestId: error instanceof ApiRequestError ? error.requestId : undefined,
  };
}

export function TopicList() {
  const [includeArchived, setIncludeArchived] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [state, setState] = useState<TopicListState>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  const generation = useRef(0);
  const firstController = useRef<AbortController | null>(null);
  const moreController = useRef<AbortController | null>(null);
  const morePending = useRef(false);

  useEffect(() => {
    const current = ++generation.current;
    const controller = new AbortController();
    firstController.current = controller;
    void listMonitorTopics(
      { include_archived: includeArchived, limit: 20 },
      { signal: controller.signal },
    )
      .then((page) => {
        if (current === generation.current && !controller.signal.aborted)
          setState({
            status: "ready",
            topics: page.items,
            nextCursor: page.next_cursor,
          });
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (current === generation.current && !controller.signal.aborted) {
          const failure = toFailure(error);
          toast.error(failure.message, {
            description: failure.requestId
              ? `请求编号：${failure.requestId}`
              : undefined,
          });
          setState({ status: "error", ...failure });
        }
      });
    return () => {
      controller.abort();
      moreController.current?.abort();
    };
  }, [includeArchived, reloadVersion]);

  function resetList(archived: boolean = includeArchived) {
    ++generation.current;
    firstController.current?.abort();
    moreController.current?.abort();
    morePending.current = false;
    setLoadingMore(false);
    setState({ status: "loading" });
    if (archived === includeArchived) setReloadVersion((value) => value + 1);
    else setIncludeArchived(archived);
  }

  async function loadMore() {
    if (state.status !== "ready" || !state.nextCursor || morePending.current)
      return;
    const current = generation.current;
    const cursor = state.nextCursor;
    const controller = new AbortController();
    moreController.current = controller;
    morePending.current = true;
    setLoadingMore(true);
    try {
      const page = await listMonitorTopics(
        { include_archived: includeArchived, limit: 20, cursor },
        { signal: controller.signal },
      );
      if (current !== generation.current || controller.signal.aborted) return;
      setState((previous) =>
        previous.status === "ready"
          ? {
              status: "ready",
              topics: Array.from(
                new Map(
                  [...previous.topics, ...page.items].map((topic) => [
                    topic.id,
                    topic,
                  ]),
                ).values(),
              ),
              nextCursor: page.next_cursor,
            }
          : previous,
      );
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (current === generation.current && !controller.signal.aborted) {
        const failure = toFailure(error);
        toast.error(failure.message, {
          description: failure.requestId
            ? `请求编号：${failure.requestId}`
            : undefined,
        });
      }
    } finally {
      if (current === generation.current) {
        morePending.current = false;
        setLoadingMore(false);
      }
    }
  }

  return (
    <section className="mt-10" aria-labelledby="monitor-topics-heading">
      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
        <h2 id="monitor-topics-heading" className="text-xl font-normal">
          我的关注
        </h2>
        <Field orientation="horizontal" className="w-fit">
          <Switch
            id="include-archived"
            checked={includeArchived}
            onCheckedChange={(checked) => resetList(checked)}
          />
          <FieldLabel htmlFor="include-archived">显示已归档</FieldLabel>
        </Field>
      </div>
      {state.status === "loading" ? (
        <div
          className="text-muted-foreground flex items-center gap-3 text-sm"
          role="status"
        >
          <Spinner />
          正在读取关注
        </div>
      ) : null}
      {state.status === "error" ? (
        <Alert variant="destructive">
          <AlertTitle>暂时无法读取关注</AlertTitle>
          <AlertDescription>请重新加载关注列表。</AlertDescription>
          <Button
            type="button"
            variant="outline"
            size="navigation"
            onClick={() => resetList()}
          >
            <RotateCcwIcon data-icon="inline-start" />
            重新加载
          </Button>
        </Alert>
      ) : null}
      {state.status === "ready" && state.topics.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>还没有关注的话题</EmptyTitle>
            <EmptyDescription>
              创建一个关注，设置关键词和信息来源。
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button asChild size="hero">
              <Link href="/monitors/new">创建关注</Link>
            </Button>
          </EmptyContent>
        </Empty>
      ) : null}
      {state.status === "ready" && state.topics.length > 0 ? (
        <ItemGroup>
          {state.topics.map((topic) => (
            <div key={topic.id} role="listitem">
              <Item asChild>
                <Link href={`/monitors/${topic.id}`}>
                  <ItemContent>
                    <ItemTitle>
                      {topic.name}
                      <Badge variant="secondary">
                        {topic.status === "archived"
                          ? "已归档"
                          : topic.status === "active"
                            ? "关注中"
                            : "已暂停"}
                      </Badge>
                    </ItemTitle>
                    <ItemDescription>
                      {[...topic.rules.match_any, ...topic.rules.match_all]
                        .slice(0, 3)
                        .join(" · ") || "查看关键词"}{" "}
                      ·{" "}
                      {topic.source_keys.length
                        ? `${topic.source_keys.length} 个来源`
                        : "待设置来源"}
                    </ItemDescription>
                  </ItemContent>
                  <ItemActions>
                    <ArrowRightIcon aria-hidden="true" />
                  </ItemActions>
                </Link>
              </Item>
            </div>
          ))}
        </ItemGroup>
      ) : null}
      {state.status === "ready" && state.nextCursor ? (
        <Button
          type="button"
          variant="outline"
          size="navigation"
          className="mt-8"
          onClick={() => void loadMore()}
          disabled={loadingMore}
        >
          {loadingMore ? (
            <Spinner data-icon="inline-start" aria-hidden="true" />
          ) : null}
          {loadingMore ? "正在读取" : "加载更多"}
        </Button>
      ) : null}
    </section>
  );
}
