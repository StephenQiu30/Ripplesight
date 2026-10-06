"use client";
import * as UI from "@/components/ui/content";

import {
  Item,
  ItemContent,
  ItemTitle,
  ItemDescription,
} from "@/components/ui/item";
import { ChevronDownIcon } from "lucide-react";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { FieldLabel, Field } from "@/components/ui/field";

import { useId, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { listEventMembers } from "@/api/shijian";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import {
  EventSectionFailure,
  EventTimeline,
} from "@/components/events/event-reading";
import {
  safeEventUrl,
  sourceTimeline,
  workbenchSources,
} from "@/components/events/reading-model";
import { ApiRequestError } from "@/request";

type MemberState =
  | { status: "loading" }
  | { status: "error"; error: unknown }
  | { status: "ready"; page: HotKeyAPI.EventMemberPageView };

const scopeLabels: Record<HotKeyAPI.ContentTextScope, string> = {
  full: "全文",
  summary: "来源摘要",
  truncated: "截断正文",
  media_only: "媒体内容",
};
const visibilityLabels: Record<HotKeyAPI.ContentVisibilityStatus, string> = {
  visible: "来源仍可见",
  deleted: "来源已删除",
  restricted: "来源限制访问",
  transient_failure: "最近访问暂时失败",
  unknown: "来源可见性未知",
};

function errorMessage(error: unknown): string {
  return error instanceof ApiRequestError
    ? `${error.message}${error.requestId ? ` 请求编号：${error.requestId}` : ""}`
    : "成员证据读取失败，请稍后重试。";
}

export function EventMemberList({
  eventId,
  revision,
  selectedContentIds = [],
  onToggleContent,
  onMembersLoaded,
}: {
  eventId: string;
  revision: number;
  selectedContentIds?: string[];
  onToggleContent?: (contentId: string) => void;
  onMembersLoaded?: (members: HotKeyAPI.EventMemberReadView[]) => void;
}) {
  const fieldId = useId();

  const [state, setState] = useState<MemberState>({ status: "loading" });
  const [retry, setRetry] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    void listEventMembers(
      { event_id: eventId, revision, limit: 20 },
      { signal: current.signal },
    )
      .then((page) => {
        if (!current.signal.aborted) {
          setState({ status: "ready", page });
          onMembersLoaded?.(page.items);
        }
      })
      .catch((error: unknown) => {
        if (
          !current.signal.aborted &&
          !(error instanceof ApiRequestError && error.kind === "cancelled")
        ) {
          setState({ status: "error", error });
          toast.error(errorMessage(error));
        }
      });
    return () => current.abort();
  }, [eventId, revision, retry, onMembersLoaded]);

  async function loadMore() {
    if (state.status !== "ready" || !state.page.next_cursor || loadingMore)
      return;
    const signal = controller.current?.signal;
    setLoadingMore(true);
    try {
      const page = await listEventMembers(
        {
          event_id: eventId,
          revision,
          limit: 20,
          cursor: state.page.next_cursor,
        },
        { signal },
      );
      if (!signal?.aborted) {
        const items = [
          ...new Map(
            [...state.page.items, ...page.items].map((item) => [item.id, item]),
          ).values(),
        ];
        setState({ status: "ready", page: { ...page, items } });
        onMembersLoaded?.(items);
      }
    } catch (error: unknown) {
      if (
        !signal?.aborted &&
        !(error instanceof ApiRequestError && error.kind === "cancelled")
      )
        toast.error(errorMessage(error));
    } finally {
      if (!signal?.aborted) setLoadingMore(false);
    }
  }

  if (state.status === "loading")
    return (
      <UI.Content
        aria-label="正在读取成员证据"
        role="status"
        aria-busy="true"
        className="flex flex-col gap-5"
      >
        <Skeleton className="h-40 w-full motion-reduce:animate-none" />
        <Skeleton className="h-40 w-full motion-reduce:animate-none" />
      </UI.Content>
    );
  if (state.status === "error")
    return (
      <EventSectionFailure
        title="无法读取此修订成员"
        error={state.error}
        retry={() => {
          setState({ status: "loading" });
          setRetry((value) => value + 1);
        }}
      />
    );
  return (
    <UI.Content className="flex flex-col gap-6">
      <EventTimeline
        entries={sourceTimeline(workbenchSources(state.page.items))}
      />
      <UI.Text tone="muted" size="sm">
        正在阅读修订 {state.page.revision} 的固定成员。
      </UI.Text>
      {state.page.current_revision !== state.page.revision ? (
        <Alert>
          <AlertTitle>当前展示历史成员</AlertTitle>
          <AlertDescription>
            事件最新修订为 {state.page.current_revision}
            。本页保持所选修订的成员证据，刷新事件详情可读取最新成员。
          </AlertDescription>
        </Alert>
      ) : null}
      {state.page.evidence_state === "partial" ? (
        <Alert role="status">
          <AlertDescription>此修订的部分成员证据已不可读。</AlertDescription>
        </Alert>
      ) : null}
      <UI.Heading>固定版本证据</UI.Heading>
      {state.page.items.map((member) => (
        <UI.Content key={member.id} className="flex flex-col gap-y-3">
          {onToggleContent && member.availability === "readable" ? (
            <Field orientation="horizontal" className="w-auto">
              <Checkbox
                checked={selectedContentIds.includes(member.content_id)}
                onCheckedChange={() => onToggleContent(member.content_id)}
                id={`${fieldId}-${member.id}`}
              />
              <FieldLabel htmlFor={`${fieldId}-${member.id}`}>
                选择此成员进行人工修订
              </FieldLabel>
            </Field>
          ) : null}
          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                className="h-auto justify-start whitespace-normal"
              >
                读取固定证据：
                {member.content?.observation.content_version?.title ??
                  "成员证据暂不可读"}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent
              forceMount
              className="data-[state=closed]:hidden"
            >
              <MemberReading member={member} />
            </CollapsibleContent>
          </Collapsible>
        </UI.Content>
      ))}
      {state.page.next_cursor ? (
        <Button
          variant="outline"
          disabled={loadingMore}
          onClick={() => void loadMore()}
        >
          {loadingMore ? "正在读取更多成员…" : "加载更多成员"}
        </Button>
      ) : null}
    </UI.Content>
  );
}

function MemberReading({ member }: { member: HotKeyAPI.EventMemberReadView }) {
  const reading = member.content;
  if (!reading || member.availability === "unavailable")
    return (
      <Item variant="default" asChild>
        <UI.Content as="article" className="px-0 py-4">
          <ItemContent className="min-w-0 gap-3">
            <ItemTitle className="line-clamp-none w-full">
              <UI.Heading level={3}>该成员证据暂不可读</UI.Heading>
            </ItemTitle>
            <ItemDescription className="mt-3 line-clamp-none">
              固定版本的观察已失效或被移除，不以新版内容替代。
            </ItemDescription>
          </ItemContent>
        </UI.Content>
      </Item>
    );
  const observation = reading.observation;
  const version = observation.content_version;
  const originalUrl =
    safeEventUrl(observation.canonical_url) ??
    safeEventUrl(observation.final_url);
  const metrics = observation.metrics;
  const metricValues = [
    ["点赞", metrics.like_count],
    ["评论", metrics.comment_count],
    ["转发", metrics.repost_count],
    ["浏览", metrics.view_count],
    ["播放", metrics.play_count],
    ["弹幕", metrics.danmaku_count],
  ] as const;
  return (
    <Item variant="default" asChild>
      <UI.Content as="article" className="px-0 py-4">
        <ItemContent className="min-w-0 gap-3">
          <UI.Content className="flex flex-wrap gap-3">
            <Badge variant="secondary">{reading.source_key}</Badge>
            {version ? (
              <Badge variant="secondary">
                {scopeLabels[version.text_scope]}
              </Badge>
            ) : null}
            <Badge variant="secondary">
              {member.assignment_origin === "manual" ? "人工归入" : "模型归并"}
            </Badge>
          </UI.Content>
          <ItemTitle className="line-clamp-none w-full">
            <UI.Heading level={3} className="mt-5">
              {version?.title ?? "成员内容"}
            </UI.Heading>
          </ItemTitle>
          <ItemDescription className="mt-3 line-clamp-none">
            {observation.author_external_id
              ? `作者：${observation.author_external_id} · `
              : ""}
            观察于{" "}
            <UI.InlineCode>
              {new Date(observation.observed_at).toLocaleString("zh-CN")}
            </UI.InlineCode>
          </ItemDescription>
          {version?.text_scope === "summary" ||
          version?.text_scope === "truncated" ? (
            <ItemDescription className="mt-4 line-clamp-none">
              此版本为{scopeLabels[version.text_scope]}，正文不代表完整原文。
            </ItemDescription>
          ) : null}
          {version?.body ? (
            <UI.Text className="mt-5 break-words whitespace-pre-wrap">
              {version.body}
            </UI.Text>
          ) : (
            <ItemDescription className="mt-5 line-clamp-none">
              此版本没有可读正文。
            </ItemDescription>
          )}
          {version?.text_origin === "machine_extracted" ? (
            <ItemDescription className="mt-4 line-clamp-none">
              正文由机器提取。依据：{version.text_origin_ref}
            </ItemDescription>
          ) : null}
          <UI.Content className="mt-6 flex flex-wrap gap-x-5 gap-y-2">
            {metricValues.map(([label, count]) => (
              <UI.Text as="span" size="sm" tone="muted" key={label}>
                {label}：
                <UI.InlineCode>{count === null ? "未知" : count}</UI.InlineCode>
              </UI.Text>
            ))}
          </UI.Content>
          {reading.current_visibility ? (
            <ItemDescription className="mt-4 line-clamp-none">
              {visibilityLabels[reading.current_visibility.status]}，状态观察于{" "}
              <UI.InlineCode>
                {new Date(
                  reading.current_visibility.observed_at,
                ).toLocaleString("zh-CN")}
              </UI.InlineCode>
            </ItemDescription>
          ) : null}
          {version?.relations.length ? (
            <UI.Content className="mt-6 flex flex-col gap-y-2">
              {version.relations.map((relation, index) => (
                <UI.Text
                  key={`${relation.relation_type}:${relation.target_external_id}:${index}`}
                  tone="muted"
                  size="sm"
                >
                  {relation.relation_type === "quote" ? "引用" : "转帖"}：
                  {relation.target_external_id}
                  {relation.target_content_id ? (
                    <UI.TextLink
                      href={`/content/${relation.target_content_id}`}
                      className="ml-3"
                    >
                      查看引用内容
                    </UI.TextLink>
                  ) : (
                    "（本地引用证据不可读）"
                  )}
                </UI.Text>
              ))}
            </UI.Content>
          ) : null}
          <UI.Content className="mt-6 flex flex-wrap gap-3">
            {originalUrl ? (
              <Button asChild variant="outline">
                <UI.TextLink
                  href={originalUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  阅读原文
                </UI.TextLink>
              </Button>
            ) : null}
            <Button asChild variant="ghost">
              <UI.TextLink href={`/content/${reading.id}`}>
                查看当前内容记录
              </UI.TextLink>
            </Button>
          </UI.Content>
          <Collapsible className="mt-6">
            <CollapsibleTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
              >
                <UI.Text as="span" className="min-w-0">
                  证据记录与归入修订
                </UI.Text>
                <ChevronDownIcon aria-hidden="true" data-icon="inline-end" />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent
              forceMount
              className="data-[state=closed]:hidden"
            >
              <UI.Content className="mt-3 flex flex-col gap-y-2 break-all">
                <UI.Text size="sm" tone="muted">
                  内容版本：
                  <UI.InlineCode>{member.content_version_id}</UI.InlineCode>
                </UI.Text>
                <UI.Text size="sm" tone="muted">
                  观察：<UI.InlineCode>{observation.id}</UI.InlineCode>
                </UI.Text>
                <UI.Text>
                  加入修订：{member.added_revision}
                  {member.removed_revision
                    ? `；移除修订：${member.removed_revision}`
                    : ""}
                </UI.Text>
              </UI.Content>
            </CollapsibleContent>
          </Collapsible>
        </ItemContent>
      </UI.Content>
    </Item>
  );
}
