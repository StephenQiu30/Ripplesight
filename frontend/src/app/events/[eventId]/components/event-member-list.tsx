"use client";
import { ChevronDownIcon } from "lucide-react";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { FieldLabel, Field } from "@/components/ui/field";

import Link from "next/link";
import { useId, useEffect, useRef, useState } from "react";
import { listEventMembers } from "@/api/shijian";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/request";

type MemberState =
  | { status: "loading" }
  | { status: "error"; message: string }
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

function safeUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return ["https:", "http:"].includes(parsed.protocol) ? value : null;
  } catch {
    return null;
  }
}

export function EventMemberList({
  eventId,
  revision,
  selectedContentIds = [],
  onToggleContent,
}: {
  eventId: string;
  revision: number;
  selectedContentIds?: string[];
  onToggleContent?: (contentId: string) => void;
}) {
  const fieldId = useId();

  const [state, setState] = useState<MemberState>({ status: "loading" });
  const [retry, setRetry] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    void listEventMembers(
      { event_id: eventId, revision, limit: 20 },
      { signal: current.signal },
    )
      .then((page) => {
        if (!current.signal.aborted) setState({ status: "ready", page });
      })
      .catch((error: unknown) => {
        if (!current.signal.aborted)
          setState({ status: "error", message: errorMessage(error) });
      });
    return () => current.abort();
  }, [eventId, revision, retry]);

  async function loadMore() {
    if (state.status !== "ready" || !state.page.next_cursor || loadingMore)
      return;
    const signal = controller.current?.signal;
    setLoadingMore(true);
    setPageError(null);
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
      if (!signal?.aborted)
        setState({
          status: "ready",
          page: {
            ...page,
            items: [
              ...new Map(
                [...state.page.items, ...page.items].map((item) => [
                  item.id,
                  item,
                ]),
              ).values(),
            ],
          },
        });
    } catch (error: unknown) {
      if (!signal?.aborted) setPageError(errorMessage(error));
    } finally {
      if (!signal?.aborted) setLoadingMore(false);
    }
  }

  if (state.status === "loading")
    return (
      <div aria-label="正在读取成员证据" className="mt-8 flex flex-col gap-y-5">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  if (state.status === "error")
    return (
      <Alert variant="destructive" className="mt-8">
        <AlertTitle>无法读取此修订成员</AlertTitle>
        <AlertDescription>
          {state.message}
          <Button
            variant="outline"
            onClick={() => {
              setState({ status: "loading" });
              setRetry((value) => value + 1);
            }}
          >
            重试成员读取
          </Button>
        </AlertDescription>
      </Alert>
    );
  return (
    <div className="mt-8 flex flex-col gap-y-8">
      <p className="text-muted-foreground text-sm">
        正在阅读修订 {state.page.revision} 的固定成员。
      </p>
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
        <p role="status" className="text-muted-foreground text-sm">
          此修订的部分成员证据已不可读。
        </p>
      ) : null}
      {state.page.items.map((member) => (
        <div key={member.id} className="flex flex-col gap-y-3">
          {onToggleContent && member.availability === "readable" ? (
            <Field orientation="horizontal" className="w-auto">
              <Checkbox
                checked={selectedContentIds.includes(member.content_id)}
                onCheckedChange={() => onToggleContent(member.content_id)}
                id={`${fieldId}-event-member-list-field-1`}
              />
              <FieldLabel htmlFor={`${fieldId}-event-member-list-field-1`}>
                选择此成员进行人工修订
              </FieldLabel>
            </Field>
          ) : null}
          <MemberReading member={member} />
        </div>
      ))}
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
          {loadingMore ? "正在读取更多成员…" : "加载更多成员"}
        </Button>
      ) : null}
    </div>
  );
}

function MemberReading({ member }: { member: HotKeyAPI.EventMemberReadView }) {
  const reading = member.content;
  if (!reading || member.availability === "unavailable")
    return (
      <article className="bg-muted/30 rounded-xl p-6">
        <h3 className="text-lg font-medium">该成员证据暂不可读</h3>
        <p className="text-muted-foreground mt-3 leading-7">
          固定版本的观察已失效或被移除，不以新版内容替代。
        </p>
      </article>
    );
  const observation = reading.observation;
  const version = observation.content_version;
  const originalUrl =
    safeUrl(observation.canonical_url) ?? safeUrl(observation.final_url);
  const comment = reading.representative_comment;
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
    <article className="bg-muted/30 rounded-xl p-6 sm:p-8">
      <div className="flex flex-wrap gap-3">
        <Badge variant="secondary">{reading.source_key}</Badge>
        {version ? (
          <Badge variant="secondary">{scopeLabels[version.text_scope]}</Badge>
        ) : null}
        <Badge variant="secondary">
          {member.assignment_origin === "manual" ? "人工归入" : "模型归并"}
        </Badge>
      </div>
      <h3 className="mt-5 text-xl font-medium">
        {version?.title ?? "成员内容"}
      </h3>
      <p className="text-muted-foreground mt-3 text-sm">
        {observation.author_external_id
          ? `作者：${observation.author_external_id} · `
          : ""}
        观察于 {new Date(observation.observed_at).toLocaleString("zh-CN")}
      </p>
      {version?.text_scope === "summary" ||
      version?.text_scope === "truncated" ? (
        <p className="text-muted-foreground mt-4 text-sm">
          此版本为{scopeLabels[version.text_scope]}，正文不代表完整原文。
        </p>
      ) : null}
      {version?.body ? (
        <p className="mt-5 leading-8 break-words whitespace-pre-wrap">
          {version.body}
        </p>
      ) : (
        <p className="text-muted-foreground mt-5">此版本没有可读正文。</p>
      )}
      {version?.text_origin === "machine_extracted" ? (
        <p className="text-muted-foreground mt-4 text-sm">
          正文由机器提取。依据：{version.text_origin_ref}
        </p>
      ) : null}
      <div className="text-muted-foreground mt-6 flex flex-wrap gap-x-5 gap-y-2 text-sm">
        {metricValues.map(([label, count]) => (
          <span key={label}>
            {label}：{count === null ? "未知" : count}
          </span>
        ))}
      </div>
      {reading.current_visibility ? (
        <p className="text-muted-foreground mt-4 text-sm">
          {visibilityLabels[reading.current_visibility.status]}，状态观察于{" "}
          {new Date(reading.current_visibility.observed_at).toLocaleString(
            "zh-CN",
          )}
        </p>
      ) : null}
      {version?.relations.length ? (
        <div className="mt-6 flex flex-col gap-y-2">
          {version.relations.map((relation, index) => (
            <p
              key={`${relation.relation_type}:${relation.target_external_id}:${index}`}
              className="text-muted-foreground text-sm"
            >
              {relation.relation_type === "quote" ? "引用" : "转帖"}：
              {relation.target_external_id}
              {relation.target_content_id ? (
                <Link
                  href={`/content/${relation.target_content_id}`}
                  className="ml-3 underline underline-offset-4"
                >
                  查看引用内容
                </Link>
              ) : (
                "（本地引用证据不可读）"
              )}
            </p>
          ))}
        </div>
      ) : null}
      {comment ? (
        <section
          aria-label="代表评论"
          className="bg-background/70 mt-6 rounded-lg p-5"
        >
          <h4 className="font-medium">代表评论的最新可读观察</h4>
          <p className="text-muted-foreground mt-2 text-sm">
            观察于{" "}
            {new Date(comment.observation.observed_at).toLocaleString("zh-CN")}
            ；评论未固定到事件成员版本。
          </p>
          <p className="mt-3 leading-7 break-words whitespace-pre-wrap">
            {comment.observation.content_version?.body ??
              comment.observation.content_version?.title ??
              "无可读评论正文"}
          </p>
        </section>
      ) : reading.representative_comment_state === "unavailable" ? (
        <p className="text-muted-foreground mt-6 text-sm">
          代表评论证据暂不可读。
        </p>
      ) : null}
      <div className="mt-6 flex flex-wrap gap-3">
        {originalUrl ? (
          <Button asChild variant="outline">
            <a href={originalUrl} target="_blank" rel="noopener noreferrer">
              阅读原文
            </a>
          </Button>
        ) : null}
        <Button asChild variant="ghost">
          <Link href={`/content/${reading.id}`}>查看当前内容记录</Link>
        </Button>
      </div>
      <Collapsible className="text-muted-foreground mt-6 text-sm">
        <CollapsibleTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
          >
            <span className="min-w-0 text-left">证据记录与归入修订</span>
            <ChevronDownIcon
              aria-hidden="true"
              data-icon="inline-end"
              className="group-data-[state=open]:rotate-180"
            />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent forceMount className="data-[state=closed]:hidden">
          <div className="mt-3 flex flex-col gap-y-2 break-all">
            <p>内容版本：{member.content_version_id}</p>
            <p>观察：{observation.id}</p>
            <p>
              加入修订：{member.added_revision}
              {member.removed_revision
                ? `；移除修订：${member.removed_revision}`
                : ""}
            </p>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </article>
  );
}
