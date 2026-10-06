"use client";

import { useId, useEffect, useState } from "react";
import { listEventFacts } from "@/api/shijian";
import * as UI from "@/components/ui/content";
import { ItemGroup } from "@/components/ui/item";
import { FieldLabel, Field } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import {
  EventEmpty,
  EventSectionFailure,
  FactSummary,
} from "@/components/events/event-reading";
import type { EventSource } from "@/components/events/reading-model";
import { ApiRequestError } from "@/request";

const relationLabels = {
  root: "根事实",
  development: "直接进展",
  background: "背景",
  roundup: "盘点",
  unreviewed: "待复核",
};

export function EventFacts({
  eventId,
  revision,
  sources,
  selectedFactIds,
  onToggleFact,
  onFactsLoaded,
}: {
  eventId: string;
  revision: number;
  sources: EventSource[];
  selectedFactIds: string[];
  onToggleFact?: (factId: string) => void;
  onFactsLoaded: (facts: HotKeyAPI.EventFactView[]) => void;
}) {
  const fieldId = useId();
  const [facts, setFacts] = useState<HotKeyAPI.EventFactView[] | null>(null);
  const [failure, setFailure] = useState<{ error: unknown } | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void listEventFacts(
      { event_id: eventId, revision },
      { signal: controller.signal },
    )
      .then((page) => {
        if (controller.signal.aborted) return;
        setFacts(page.facts);
        onFactsLoaded(page.facts);
      })
      .catch((error: unknown) => {
        if (
          !controller.signal.aborted &&
          !(error instanceof ApiRequestError && error.kind === "cancelled")
        )
          setFailure({ error });
      });
    return () => controller.abort();
  }, [eventId, revision, retry, onFactsLoaded]);
  return (
    <UI.Content
      as="section"
      className="flex flex-col gap-4"
      aria-labelledby="event-facts-heading"
    >
      <UI.Heading id="event-facts-heading">事实与进展</UI.Heading>
      <UI.Text size="sm" tone="muted">
        重复报道归于同一事实；引用编号可跳到固定来源。
      </UI.Text>
      {failure ? (
        <EventSectionFailure
          title="无法读取事实"
          error={failure.error}
          retry={() => {
            setFailure(null);
            setFacts(null);
            setRetry((value) => value + 1);
          }}
        />
      ) : facts === null ? (
        <Skeleton
          aria-label="正在读取事实"
          className="h-24 w-full motion-reduce:animate-none"
        />
      ) : !facts.length ? (
        <EventEmpty>当前事件尚无细分事实关系。</EventEmpty>
      ) : (
        <ItemGroup>
          {facts.map((fact) => (
            <FactSummary
              key={fact.id}
              title={fact.title ?? "事实文本待复核或不可读"}
              summary={fact.summary}
              sources={sources.filter((source) =>
                fact.members.some(
                  (member) => member.event_member_id === source.id,
                ),
              )}
            >
              <UI.Content className="flex flex-wrap items-center gap-3">
                {onToggleFact ? (
                  <Field orientation="horizontal" className="w-auto">
                    <Checkbox
                      checked={selectedFactIds.includes(fact.id)}
                      onCheckedChange={() => onToggleFact(fact.id)}
                      id={`${fieldId}-${fact.id}`}
                    />
                    <FieldLabel htmlFor={`${fieldId}-${fact.id}`}>
                      选择事实
                    </FieldLabel>
                  </Field>
                ) : null}
                <Badge variant="secondary">
                  {relationLabels[fact.relation]}
                </Badge>
                <UI.Text size="sm" tone="muted">
                  <UI.InlineCode>{fact.members.length}</UI.InlineCode>{" "}
                  份固定证据 · 事实修订{" "}
                  <UI.InlineCode>{fact.revision}</UI.InlineCode>
                </UI.Text>
              </UI.Content>
              {fact.root_fact_id ? (
                <UI.Text size="sm" tone="muted">
                  直接关联根事实：
                  {facts.find((candidate) => candidate.id === fact.root_fact_id)
                    ?.title ?? fact.root_fact_id}
                </UI.Text>
              ) : null}
              {fact.evidence_state === "partial" ? (
                <UI.Text size="sm" tone="muted">
                  部分固定证据已不可读，派生事实文本隐藏。
                </UI.Text>
              ) : null}
            </FactSummary>
          ))}
        </ItemGroup>
      )}
    </UI.Content>
  );
}
