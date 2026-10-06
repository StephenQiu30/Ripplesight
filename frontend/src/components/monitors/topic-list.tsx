"use client";
import * as UI from "@/components/ui/content";

import { toast } from "sonner";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, RotateCcwIcon } from "lucide-react";

import { listMonitorTopics } from "@/api/jiankongzhuti";
import { PageState } from "@/components/system/page-state";
import {
  readMonitorFailure,
  presentUpdatedTopic,
  topicStatusLabel,
  type MonitorFailure,
} from "./monitor-presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

type TopicListState =
  | { status: "loading" }
  | {
      status: "ready";
      topics: HotKeyAPI.MonitorTopicView[];
      nextCursor: string | null;
    }
  | ({ status: "error" } & MonitorFailure);

function toFailure(error: unknown) {
  return readMonitorFailure(error, "关注列表加载失败，请稍后重试。");
}

export function TopicList({
  selectedTopicId,
  onFirstTopic,
  updatedTopics,
  onForbidden,
}: {
  selectedTopicId?: string;
  onFirstTopic?: (id: string | undefined) => void;
  updatedTopics?: Record<string, HotKeyAPI.MonitorTopicView>;
  onForbidden?: (forbidden: boolean) => void;
} = {}) {
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
        if (current === generation.current && !controller.signal.aborted) {
          onFirstTopic?.(page.items[0]?.id);
          onForbidden?.(false);
          setState({
            status: "ready",
            topics: page.items,
            nextCursor: page.next_cursor,
          });
        }
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (current === generation.current && !controller.signal.aborted) {
          const failure = toFailure(error);
          if (failure.forbidden) onForbidden?.(true);
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
  }, [includeArchived, reloadVersion, onFirstTopic, onForbidden]);

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

  const topics =
    state.status === "ready"
      ? state.topics
          .map((topic) => presentUpdatedTopic(topic, updatedTopics?.[topic.id]))
          .filter((topic) => includeArchived || topic.status !== "archived")
      : [];
  return (
    <UI.Content
      as="section"
      className="flex min-w-0 flex-col gap-5"
      aria-labelledby="monitor-topics-heading"
    >
      <UI.Content className="flex flex-wrap items-center justify-between gap-4">
        <UI.Heading level={2} id="monitor-topics-heading">
          主题列表
        </UI.Heading>
        <Field orientation="horizontal" className="w-fit">
          <Switch
            id="include-archived"
            checked={includeArchived}
            onCheckedChange={(checked) => resetList(checked)}
          />
          <FieldLabel htmlFor="include-archived">显示已归档</FieldLabel>
        </Field>
      </UI.Content>
      {state.status === "loading" && (
        <PageState
          headingLevel={2}
          state="loading"
          eyebrow="监控主题"
          title="正在读取关注"
          description="正在读取主题列表。"
        />
      )}
      {state.status === "error" && (
        <PageState
          headingLevel={2}
          state={state.forbidden ? "forbidden" : "error"}
          eyebrow="监控主题"
          title={state.forbidden ? "无权读取监控主题" : "暂时无法读取关注"}
          description={
            state.forbidden
              ? "请登录有权访问这些主题的账户。"
              : "请重新加载关注列表。"
          }
          errorCode={state.code}
          httpStatus={state.httpStatus}
          action={
            state.forbidden ? undefined : (
              <Button
                type="button"
                variant="outline"
                size="navigation"
                onClick={() => resetList()}
              >
                <RotateCcwIcon data-icon="inline-start" />
                重新加载
              </Button>
            )
          }
        />
      )}
      {state.status === "ready" && topics.length === 0 && (
        <PageState
          headingLevel={2}
          state="empty"
          eyebrow="监控主题"
          title="还没有关注的话题"
          description="创建一个关注，设置关键词和信息来源。"
          action={
            <Button asChild>
              <Link href="/monitors/new">创建关注</Link>
            </Button>
          }
        />
      )}
      {state.status === "ready" && topics.length > 0 ? (
        <ItemGroup>
          {topics.map((topic) => (
            <UI.Content key={topic.id} role="listitem">
              <Item
                asChild
                variant={selectedTopicId === topic.id ? "muted" : "default"}
              >
                <Link
                  href={`/monitors/${topic.id}`}
                  aria-current={
                    selectedTopicId === topic.id ? "page" : undefined
                  }
                >
                  <ItemContent>
                    <ItemTitle>
                      {topic.name}
                      <Badge variant="secondary">
                        {topicStatusLabel(topic.status)}
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
            </UI.Content>
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
    </UI.Content>
  );
}
