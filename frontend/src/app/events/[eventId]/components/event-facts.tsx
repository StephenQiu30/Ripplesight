"use client";
import {
  Item,
  ItemContent,
  ItemGroup,
  ItemTitle,
  ItemDescription,
} from "@/components/ui/item";
import { FieldLabel, Field } from "@/components/ui/field";

import { useId, useEffect, useState } from "react";
import { toast } from "sonner";
import { listEventFacts } from "@/api/shijian";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
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
  selectedFactIds,
  onToggleFact,
  onFactsLoaded,
}: {
  eventId: string;
  revision: number;
  selectedFactIds: string[];
  onToggleFact?: (factId: string) => void;
  onFactsLoaded: (facts: HotKeyAPI.EventFactView[]) => void;
}) {
  const fieldId = useId();

  const [facts, setFacts] = useState<HotKeyAPI.EventFactView[] | null>(null);
  const [failed, setFailed] = useState(false);
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
      .catch((failure: unknown) => {
        if (
          !controller.signal.aborted &&
          !(failure instanceof ApiRequestError && failure.kind === "cancelled")
        ) {
          setFailed(true);
          toast.error(
            failure instanceof ApiRequestError
              ? failure.message
              : "事实关系暂时读取失败。",
          );
        }
      });
    return () => controller.abort();
  }, [eventId, revision, retry, onFactsLoaded]);
  return (
    <section className="mt-12" aria-labelledby="event-facts-heading">
      <h2 id="event-facts-heading" className="text-2xl font-medium">
        事实与进展
      </h2>
      <p className="text-muted-foreground mt-3 leading-7">
        重复报道归于同一事实；直接进展和背景保留各自身份与根事实关系。
      </p>
      {failed ? (
        <Alert className="mt-6" variant="destructive">
          <AlertTitle>无法读取事实</AlertTitle>
          <AlertDescription>
            可以重新读取所选修订的事实关系。
            <Button
              variant="outline"
              onClick={() => {
                setFailed(false);
                setFacts(null);
                setRetry((value) => value + 1);
              }}
            >
              重试事实读取
            </Button>
          </AlertDescription>
        </Alert>
      ) : facts === null ? (
        <Skeleton className="mt-6 h-24 w-full" />
      ) : facts.length === 0 ? (
        <p className="text-muted-foreground mt-6">当前事件尚无细分事实关系。</p>
      ) : (
        <ItemGroup className="mt-6 flex flex-col gap-y-7">
          {facts.map((fact) => (
            <Item
              role="listitem"
              variant="default"
              key={fact.id}
              className="flex flex-col gap-y-3"
            >
              <ItemContent className="min-w-0 gap-3">
                <div className="flex flex-wrap items-center gap-3">
                  {onToggleFact ? (
                    <Field orientation="horizontal" className="w-auto">
                      <Checkbox
                        checked={selectedFactIds.includes(fact.id)}
                        onCheckedChange={() => onToggleFact(fact.id)}
                        id={`${fieldId}-event-facts-field-1`}
                      />
                      <FieldLabel htmlFor={`${fieldId}-event-facts-field-1`}>
                        选择事实
                      </FieldLabel>
                    </Field>
                  ) : null}
                  <Badge variant="secondary">
                    {relationLabels[fact.relation]}
                  </Badge>
                  <span className="text-muted-foreground text-sm">
                    {fact.members.length} 份固定证据 · 事实修订 {fact.revision}
                  </span>
                </div>
                <ItemTitle className="line-clamp-none w-full">
                  <h3>{fact.title ?? "事实文本待复核或不可读"}</h3>
                </ItemTitle>
                {fact.summary ? (
                  <ItemDescription className="line-clamp-none leading-7 whitespace-pre-wrap">
                    {fact.summary}
                  </ItemDescription>
                ) : null}
                {fact.root_fact_id ? (
                  <ItemDescription className="line-clamp-none">
                    直接关联根事实：
                    {facts.find(
                      (candidate) => candidate.id === fact.root_fact_id,
                    )?.title ?? fact.root_fact_id}
                  </ItemDescription>
                ) : null}
                {fact.evidence_state === "partial" ? (
                  <ItemDescription className="line-clamp-none">
                    部分固定证据已不可读，派生事实文本隐藏。
                  </ItemDescription>
                ) : null}
              </ItemContent>
            </Item>
          ))}
        </ItemGroup>
      )}
    </section>
  );
}
