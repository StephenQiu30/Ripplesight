"use client";
import * as UI from "@/components/ui/content";

import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";
import { toast } from "sonner";
import { getEvent } from "@/api/shijian";
import { EventHeat } from "./event-heat";
import { EventMemberList } from "@/app/events/[eventId]/components/event-member-list";
import { EventFacts } from "@/app/events/[eventId]/components/event-facts";
import { EventCorrections } from "@/app/events/[eventId]/components/event-corrections";
import { PageState } from "@/components/system/page-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FieldGroup, Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiRequestError } from "@/request";

type DetailState =
  | { status: "loading" }
  | { status: "ready"; event: HotKeyAPI.EventReadView }
  | { status: "not-found" }
  | { status: "error" };

export function EventDetail({ eventId }: { eventId: string }) {
  const [state, setState] = useState<DetailState>({ status: "loading" });
  const [retry, setRetry] = useState(0);
  function refresh() {
    setState({ status: "loading" });
    setRetry((value) => value + 1);
  }

  useEffect(() => {
    const controller = new AbortController();
    void getEvent({ event_id: eventId }, { signal: controller.signal })
      .then((event) => {
        if (!controller.signal.aborted) setState({ status: "ready", event });
      })
      .catch((error: unknown) => {
        if (
          controller.signal.aborted ||
          (error instanceof ApiRequestError && error.kind === "cancelled")
        )
          return;
        if (
          error instanceof ApiRequestError &&
          error.code === "resource_not_found"
        ) {
          setState({ status: "not-found" });
        } else {
          setState({ status: "error" });
          toast.error(
            error instanceof ApiRequestError
              ? `${error.message}${error.requestId ? ` 请求编号：${error.requestId}` : ""}`
              : "事件详情读取失败，请稍后重试。",
          );
        }
      });
    return () => controller.abort();
  }, [eventId, retry]);

  if (state.status === "not-found" || state.status === "error")
    return (
      <PageState
        eyebrow="事件读取"
        title={
          state.status === "not-found" ? "事件不存在或暂不可读" : "无法读取事件"
        }
        description={
          state.status === "not-found"
            ? "此事件不存在于当前工作区，或其固定成员证据已经不可读。"
            : "可以重试详情读取，或返回事件列表。"
        }
        action={
          <UI.Content className="flex flex-wrap gap-3">
            <Button onClick={refresh}>重试事件详情</Button>
            <Button asChild variant="outline">
              <Link href="/events">返回事件列表</Link>
            </Button>
          </UI.Content>
        }
      />
    );

  return (
    <UI.Content>
      <UI.Content className="mb-8 flex flex-wrap justify-between gap-4">
        <Button asChild variant="ghost">
          <Link href="/events">返回事件列表</Link>
        </Button>
        <Button variant="outline" onClick={refresh}>
          刷新事件详情
        </Button>
      </UI.Content>
      {state.status === "loading" ? (
        <UI.Content
          aria-label="正在读取事件详情"
          className="flex flex-col gap-y-6"
        >
          <Skeleton className="h-12 w-3/4" />
          <Skeleton className="h-32 w-full" />
        </UI.Content>
      ) : (
        <EventReading
          key={`${state.event.id}:${state.event.revision}`}
          event={state.event}
          onChanged={refresh}
        />
      )}
    </UI.Content>
  );
}

function EventReading({
  event,
  onChanged,
}: {
  event: HotKeyAPI.EventReadView;
  onChanged: () => void;
}) {
  const [revision, setRevision] = useState(event.revision);
  const [revisionInput, setRevisionInput] = useState(String(event.revision));
  const [selectedContentIds, setSelectedContentIds] = useState<string[]>([]);
  const [selectedFactIds, setSelectedFactIds] = useState<string[]>([]);
  const [facts, setFacts] = useState<HotKeyAPI.EventFactView[]>([]);
  function selectRevision(form: FormEvent<HTMLFormElement>) {
    form.preventDefault();
    const selected = Number(revisionInput);
    if (
      !Number.isInteger(selected) ||
      selected < 1 ||
      selected > event.revision
    ) {
      toast.error(`请选择 1 至 ${event.revision} 的事件修订。`);
      return;
    }
    setRevision(selected);
    setSelectedContentIds([]);
    setSelectedFactIds([]);
  }

  return (
    <>
      {event.redirected_from_event_id ? (
        <Alert className="mb-8">
          <AlertTitle>已合并到当前事件</AlertTitle>
          <AlertDescription>
            此链接原来的事件已合并。当前展示规范事件及其成员。
            <Link
              href={`/events/${event.id}`}
              className="underline underline-offset-4"
            >
              打开规范事件链接
            </Link>
          </AlertDescription>
        </Alert>
      ) : null}
      <UI.Content className="flex flex-wrap gap-3">
        <Badge variant="secondary">修订 {event.revision}</Badge>
        <Badge variant="secondary">
          {
            { active: "活跃", watching: "关注中", settled: "暂时平稳" }[
              event.phase ?? "active"
            ]
          }
        </Badge>
        <Badge variant="secondary">
          {event.readable_member_count} / {event.member_count} 条成员可读
        </Badge>
      </UI.Content>
      <UI.Heading
        level={1}
        className="mt-5 text-3xl font-medium tracking-tight sm:text-4xl"
      >
        {event.title ?? "摘要待更新或暂不可读的事件"}
      </UI.Heading>
      {event.summary ? (
        <UI.Text className="text-muted-foreground mt-5 max-w-3xl leading-8 whitespace-pre-wrap">
          {event.summary}
        </UI.Text>
      ) : (
        <Alert className="mt-6">
          <AlertTitle>派生摘要暂不可读</AlertTitle>
          <AlertDescription>
            摘要需要重新生成，或其引用证据不可读。仍可阅读下方可用成员。
          </AlertDescription>
        </Alert>
      )}
      <UI.Text className="text-muted-foreground mt-6 text-sm">
        来源分布：
        {Object.entries(event.source_counts)
          .map(([source, count]) => `${source} ${count} 条`)
          .join(" · ")}
      </UI.Text>
      <UI.Text className="text-muted-foreground mt-2 text-sm">
        首次{event.first_seen_basis === "published" ? "发布" : "发现"}：
        {new Date(event.first_seen_at).toLocaleString("zh-CN")}
      </UI.Text>
      {event.latest_progress ? (
        <UI.Content as="section" className="mt-6">
          <UI.Heading level={2} className="text-xl font-medium">
            最新直接进展
          </UI.Heading>
          <UI.Text className="text-muted-foreground mt-3 leading-7 whitespace-pre-wrap">
            {event.latest_progress}
          </UI.Text>
        </UI.Content>
      ) : null}
      <EventHeat eventId={event.id} />
      <EventFacts
        key={`facts:${revision}`}
        eventId={event.id}
        revision={revision}
        selectedFactIds={selectedFactIds}
        onFactsLoaded={setFacts}
        onToggleFact={
          revision === event.revision
            ? (identity) =>
                setSelectedFactIds((current) =>
                  current.includes(identity)
                    ? current.filter((value) => value !== identity)
                    : [...current, identity],
                )
            : undefined
        }
      />
      <UI.Content
        as="section"
        className="mt-12"
        aria-labelledby="event-members-heading"
      >
        <UI.Heading
          level={2}
          id="event-members-heading"
          className="text-2xl font-medium"
        >
          事件成员与固定版本证据
        </UI.Heading>
        <UI.Text className="text-muted-foreground mt-3 leading-7">
          正文对应事件归并时选定的版本；观察指标和可见性分别标明时间。
        </UI.Text>
        {event.revision > 1 ? (
          <UI.Form onSubmit={selectRevision}>
            <FieldGroup className="mt-6 flex flex-row flex-wrap items-end gap-4">
              <Field className="w-40">
                <FieldLabel htmlFor="event-revision">事件修订</FieldLabel>
                <Input
                  id="event-revision"
                  type="number"
                  min={1}
                  max={event.revision}
                  value={revisionInput}
                  onChange={(input) => setRevisionInput(input.target.value)}
                />
              </Field>
              <Button variant="outline" type="submit">
                读取该修订成员
              </Button>
            </FieldGroup>
          </UI.Form>
        ) : null}
        <EventMemberList
          key={`${event.id}:${revision}`}
          eventId={event.id}
          revision={revision}
          selectedContentIds={selectedContentIds}
          onToggleContent={
            revision === event.revision
              ? (identity) =>
                  setSelectedContentIds((current) =>
                    current.includes(identity)
                      ? current.filter((value) => value !== identity)
                      : [...current, identity],
                  )
              : undefined
          }
        />
      </UI.Content>
      {revision === event.revision ? (
        <EventCorrections
          event={event}
          facts={facts}
          selectedContentIds={selectedContentIds}
          selectedFactIds={selectedFactIds}
          onChanged={onChanged}
        />
      ) : null}
    </>
  );
}
