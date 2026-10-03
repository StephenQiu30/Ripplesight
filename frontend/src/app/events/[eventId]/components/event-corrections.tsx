"use client";
import {
  SelectLabel,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { correctEvent, listEvents } from "@/api/shijian";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FieldGroup, Field, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/request";

const actionLabels = {
  split: "将所选成员拆成新事件",
  move: "将所选成员移到其他事件",
  detach: "排除所选成员，保持独立",
  merge: "将整个事件合并到其他事件",
  merge_facts: "合并所选事实",
  regroup: "重新归组所选自动成员",
};

export function EventCorrections({
  event,
  selectedContentIds,
  selectedFactIds,
  facts,
  onChanged,
}: {
  event: HotKeyAPI.EventReadView;
  selectedContentIds: string[];
  selectedFactIds: string[];
  facts: HotKeyAPI.EventFactView[];
  onChanged: () => void;
}) {
  const router = useRouter();
  const [kind, setKind] =
    useState<HotKeyAPI.EventCorrectionInput["kind"]>("split");
  const [targets, setTargets] = useState<HotKeyAPI.EventReadView[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [targetId, setTargetId] = useState("");
  const [targetFactId, setTargetFactId] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const operation = useRef<{ fingerprint: string; id: string } | null>(null);
  useEffect(() => {
    if (kind !== "merge" && kind !== "move") return;
    const controller = new AbortController();
    void listEvents(
      { topic_id: event.topic_id, limit: 50 },
      { signal: controller.signal },
    )
      .then((page) => {
        if (controller.signal.aborted) return;
        setTargets(page.items.filter((item) => item.id !== event.id));
        setCursor(page.next_cursor);
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted)
          setError(
            failure instanceof ApiRequestError
              ? failure.message
              : "目标事件读取失败。",
          );
      });
    return () => controller.abort();
  }, [event.id, event.topic_id, kind]);
  async function moreTargets() {
    if (!cursor) return;
    try {
      const page = await listEvents({
        topic_id: event.topic_id,
        limit: 50,
        cursor,
      });
      setTargets((current) => [
        ...current,
        ...page.items.filter((item) => item.id !== event.id),
      ]);
      setCursor(page.next_cursor);
    } catch (failure: unknown) {
      setError(
        failure instanceof ApiRequestError
          ? failure.message
          : "目标事件读取失败。",
      );
    }
  }
  async function submit(form: FormEvent<HTMLFormElement>) {
    form.preventDefault();
    if (submitting) return;
    const target = targets.find((item) => item.id === targetId);
    if ((kind === "merge" || kind === "move") && !target) {
      setError("请选择目标事件。");
      return;
    }
    if (
      kind === "merge_facts" &&
      (selectedFactIds.length < 2 || !selectedFactIds.includes(targetFactId))
    ) {
      setError("请选择至少两个事实，并指定其中一个作为规范事实。");
      return;
    }
    if (
      !["merge", "merge_facts"].includes(kind) &&
      !selectedContentIds.length
    ) {
      setError("请先选择可读的当前成员。");
      return;
    }
    if (!reason.trim()) {
      setError("请填写修订原因。");
      return;
    }
    const input = {
      kind,
      reason: reason.trim(),
      expected_revisions: {
        [event.id]: event.revision,
        ...(target && ["merge", "move"].includes(kind)
          ? { [target.id]: target.revision }
          : {}),
      },
      ...(kind === "merge" || kind === "move"
        ? { target_event_id: targetId }
        : {}),
      ...(!["merge", "merge_facts"].includes(kind)
        ? { content_ids: selectedContentIds }
        : {}),
      ...(kind === "merge_facts"
        ? { fact_ids: selectedFactIds, target_fact_id: targetFactId }
        : {}),
    };
    const fingerprint = JSON.stringify(input);
    if (operation.current?.fingerprint !== fingerprint)
      operation.current = { fingerprint, id: crypto.randomUUID() };
    setError(null);
    setSubmitting(true);
    try {
      const result = await correctEvent(
        { ...input, operation_id: operation.current.id },
        { headers: { "X-HotKey-CSRF": "1" } },
      );
      operation.current = null;
      if (result.target_event_id && result.target_event_id !== event.id)
        router.push(`/events/${result.target_event_id}`);
      onChanged();
    } catch (failure: unknown) {
      setError(
        failure instanceof ApiRequestError &&
          failure.code === "event_revision_conflict"
          ? "事件修订已变化。刷新详情并重新选择后再提交。"
          : failure instanceof ApiRequestError
            ? failure.message
            : "修订提交失败。重试将复用本次操作编号。",
      );
    } finally {
      setSubmitting(false);
    }
  }
  return (
    <section className="mt-12" aria-labelledby="event-correction-heading">
      <h2 id="event-correction-heading" className="text-2xl font-medium">
        人工修订
      </h2>
      <p className="text-muted-foreground mt-3 leading-7">
        已选择 {selectedContentIds.length} 个成员、{selectedFactIds.length}{" "}
        个事实。修订保留历史证据，摘要会重新生成。
      </p>
      <form onSubmit={(form) => void submit(form)}>
        <FieldGroup className="mt-6 grid max-w-2xl gap-5">
          <Field>
            <FieldLabel htmlFor="event-correction-kind">修订操作</FieldLabel>
            <Select
              value={kind}
              onValueChange={(selectedValue) =>
                setKind(selectedValue as HotKeyAPI.EventCorrectionInput["kind"])
              }
            >
              <SelectTrigger
                id="event-correction-kind"
                className="w-full min-w-0"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper">
                <SelectGroup>
                  <SelectLabel className="sr-only">修订操作</SelectLabel>
                  {Object.entries(actionLabels).map(([value, label]) => (
                    <SelectItem
                      key={value}
                      value={value}
                      className="whitespace-normal"
                    >
                      {label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
          {kind === "merge" || kind === "move" ? (
            <Field>
              <FieldLabel htmlFor="event-correction-target">
                目标事件
              </FieldLabel>
              <Select
                value={targetId}
                onValueChange={(selectedValue) =>
                  setTargetId(selectedValue === "__none__" ? "" : selectedValue)
                }
              >
                <SelectTrigger
                  id="event-correction-target"
                  className="w-full min-w-0"
                >
                  <SelectValue placeholder="选择同一关注主题中的事件" />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectGroup>
                    <SelectLabel className="sr-only">目标事件</SelectLabel>
                    <SelectItem value="__none__" className="whitespace-normal">
                      选择同一关注主题中的事件
                    </SelectItem>
                    {targets.map((target) => (
                      <SelectItem
                        key={target.id}
                        value={target.id}
                        className="whitespace-normal"
                      >
                        {target.title ?? `事件 ${target.id}`} · 修订{" "}
                        {target.revision}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              {cursor ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void moreTargets()}
                >
                  读取更多目标事件
                </Button>
              ) : null}
            </Field>
          ) : null}
          {kind === "merge_facts" ? (
            <Field>
              <FieldLabel htmlFor="event-correction-fact">规范事实</FieldLabel>
              <Select
                value={targetFactId}
                onValueChange={(selectedValue) =>
                  setTargetFactId(
                    selectedValue === "__none__" ? "" : selectedValue,
                  )
                }
              >
                <SelectTrigger
                  id="event-correction-fact"
                  className="w-full min-w-0"
                >
                  <SelectValue placeholder="从所选事实中选择" />
                </SelectTrigger>
                <SelectContent position="popper">
                  <SelectGroup>
                    <SelectLabel className="sr-only">规范事实</SelectLabel>
                    <SelectItem value="__none__" className="whitespace-normal">
                      从所选事实中选择
                    </SelectItem>
                    {facts
                      .filter((fact) => selectedFactIds.includes(fact.id))
                      .map((fact) => (
                        <SelectItem
                          key={fact.id}
                          value={fact.id}
                          className="whitespace-normal"
                        >
                          {fact.title ?? fact.id}
                        </SelectItem>
                      ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
          ) : null}
          <Field>
            <FieldLabel htmlFor="event-correction-reason">修订原因</FieldLabel>
            <Textarea
              id="event-correction-reason"
              maxLength={2000}
              value={reason}
              onChange={(input) => setReason(input.target.value)}
            />
          </Field>
          {error ? (
            <Alert variant="destructive">
              <AlertTitle>修订未完成</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <Button type="submit" disabled={submitting}>
            {submitting ? "正在提交修订…" : "提交人工修订"}
          </Button>
        </FieldGroup>
      </form>
    </section>
  );
}
