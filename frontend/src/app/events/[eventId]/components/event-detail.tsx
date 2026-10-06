"use client";

import { type FormEvent, useEffect, useState } from "react";
import { toast } from "sonner";
import { getEvent } from "@/api/shijian";
import * as UI from "@/components/ui/content";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { FieldGroup, Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { PageState } from "@/components/system/page-state";
import {
  EventColumns,
  EventHeader,
  EventSources,
  RepresentativeComments,
} from "@/components/events/event-reading";
import {
  memberComments,
  workbenchSources,
} from "@/components/events/reading-model";
import { ApiRequestError } from "@/request";
import { EventHeat } from "./event-heat";
import { EventFacts } from "./event-facts";
import { EventMemberList } from "./event-member-list";
import { EventCorrections } from "./event-corrections";
import { EventRelated } from "./event-related";

type DetailState =
  | { status: "loading" }
  | { status: "ready"; event: HotKeyAPI.EventReadView }
  | { status: "not-found" | "error" | "forbidden"; error: unknown };

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
        const known = error instanceof ApiRequestError ? error : null;
        const status =
          known?.status === 401 || known?.status === 403
            ? "forbidden"
            : known?.code === "resource_not_found" || known?.status === 404
              ? "not-found"
              : "error";
        setState({ status, error });
        if (status === "error")
          toast.error(known?.message ?? "事件详情读取失败，请稍后重试。");
      });
    return () => controller.abort();
  }, [eventId, retry]);

  if (state.status === "loading")
    return (
      <>
        <UI.Heading level={1} className="sr-only">
          正在读取事件详情
        </UI.Heading>
        <PageState
          state="loading"
          eyebrow="事件读取"
          title="正在读取事件详情"
          description="正在读取当前修订和固定版本证据。"
          loadingLayout="detail"
        />
      </>
    );
  if (state.status === "forbidden")
    return (
      <PageState
        state="forbidden"
        eyebrow="工作台"
        title="需要登录后阅读事件"
        description="个人事件和固定成员证据需要工作台会话。"
        action={
          <Button asChild>
            <UI.TextLink
              href={`/login?returnTo=${encodeURIComponent(`/events/${eventId}`)}`}
            >
              登录
            </UI.TextLink>
          </Button>
        }
      />
    );
  if (state.status !== "ready") {
    const known = state.error instanceof ApiRequestError ? state.error : null;
    return (
      <PageState
        state={state.status === "not-found" ? "empty" : "error"}
        eyebrow="事件读取"
        title={
          state.status === "not-found" ? "事件不存在或暂不可读" : "无法读取事件"
        }
        description={
          state.status === "not-found"
            ? "此事件不存在于当前工作区，或其固定成员证据已经不可读。"
            : "可以重试详情读取，或返回事件列表。"
        }
        errorCode={known?.code}
        httpStatus={known?.status}
        action={
          <UI.Content className="flex flex-wrap gap-3">
            <Button onClick={refresh}>重试事件详情</Button>
            <Button asChild variant="outline">
              <UI.TextLink href="/events">返回事件列表</UI.TextLink>
            </Button>
          </UI.Content>
        }
      />
    );
  }
  return (
    <EventReading
      key={`${state.event.id}:${state.event.revision}`}
      event={state.event}
      onChanged={refresh}
    />
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
  const [members, setMembers] = useState<HotKeyAPI.EventMemberReadView[]>([]);
  const [heat, setHeat] = useState<HotKeyAPI.EventAttentionView | null>(null);
  const [correctionsOpen, setCorrectionsOpen] = useState(false);
  const sources = workbenchSources(members, facts);
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
    if (revision === selected) return;
    setRevision(selected);
    setSelectedContentIds([]);
    setSelectedFactIds([]);
    setMembers([]);
    setFacts([]);
  }
  const toggle = (id: string, setter: typeof setSelectedContentIds) =>
    setter((current) =>
      current.includes(id)
        ? current.filter((value) => value !== id)
        : [...current, id],
    );
  return (
    <UI.Content className="flex min-w-0 flex-col gap-8">
      {event.redirected_from_event_id ? (
        <Alert>
          <AlertTitle>已合并到当前事件</AlertTitle>
          <AlertDescription>
            此链接原来的事件已合并。当前展示规范事件及其成员。
            <UI.TextLink href={`/events/${event.id}`}>
              打开规范事件链接
            </UI.TextLink>
          </AlertDescription>
        </Alert>
      ) : null}
      <EventHeader
        title={event.title ?? "摘要待更新或暂不可读的事件"}
        firstSeenAt={event.first_seen_at}
        firstSeenBasis={event.first_seen_basis}
        updatedAt={event.updated_at}
        sourceCount={Object.keys(event.source_counts).length}
        heat={heat?.participant_count ? heat.heat : null}
        revision={event.revision}
        phase={event.phase}
        href="/events"
        actions={
          <Button variant="outline" onClick={onChanged}>
            刷新事件详情
          </Button>
        }
      />
      <UI.Text size="sm" tone="muted">
        <UI.InlineCode>
          {event.readable_member_count} / {event.member_count}
        </UI.InlineCode>{" "}
        条成员可读。来源分布：
        {Object.entries(event.source_counts)
          .map(([source, count]) => `${source} ${count} 条`)
          .join(" · ") || "尚无来源"}
      </UI.Text>
      {event.revision > 1 ? (
        <UI.Form onSubmit={selectRevision}>
          <FieldGroup className="flex flex-row flex-wrap items-end gap-4">
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
      <EventColumns
        aside={
          <>
            <RepresentativeComments comments={memberComments(members)} />
            <EventRelated eventId={event.id} />
          </>
        }
      >
        <UI.Content as="section" className="flex flex-col gap-4">
          <UI.Heading>发生了什么</UI.Heading>
          {event.summary ? (
            <UI.Text className="whitespace-pre-wrap">{event.summary}</UI.Text>
          ) : (
            <Alert>
              <AlertTitle>派生摘要暂不可读</AlertTitle>
              <AlertDescription>
                摘要需要重新生成，或其引用证据不可读。仍可阅读下方可用成员。
              </AlertDescription>
            </Alert>
          )}
          {event.latest_progress ? (
            <>
              <UI.Heading level={3}>最新直接进展</UI.Heading>
              <UI.Text className="whitespace-pre-wrap">
                {event.latest_progress}
              </UI.Text>
            </>
          ) : null}
        </UI.Content>
        <EventFacts
          key={`facts:${revision}`}
          eventId={event.id}
          revision={revision}
          sources={sources}
          selectedFactIds={selectedFactIds}
          onFactsLoaded={setFacts}
          onToggleFact={
            revision === event.revision
              ? (id) => toggle(id, setSelectedFactIds)
              : undefined
          }
        />
        <EventHeat
          eventId={event.id}
          eventRevision={event.revision}
          onHeatLoaded={setHeat}
        />
        <EventMemberList
          key={`${event.id}:${revision}`}
          eventId={event.id}
          revision={revision}
          onMembersLoaded={setMembers}
          selectedContentIds={selectedContentIds}
          onToggleContent={
            revision === event.revision
              ? (id) => toggle(id, setSelectedContentIds)
              : undefined
          }
        />
        <EventSources sources={sources} />
      </EventColumns>
      {revision === event.revision ? (
        <>
          <Separator />
          <Collapsible open={correctionsOpen} onOpenChange={setCorrectionsOpen}>
            <CollapsibleTrigger asChild>
              <Button variant="ghost">人工修订与纠错</Button>
            </CollapsibleTrigger>
            <CollapsibleContent forceMount hidden={!correctionsOpen}>
              <EventCorrections
                event={event}
                facts={facts}
                selectedContentIds={selectedContentIds}
                selectedFactIds={selectedFactIds}
                onChanged={onChanged}
              />
            </CollapsibleContent>
          </Collapsible>
        </>
      ) : null}
    </UI.Content>
  );
}
