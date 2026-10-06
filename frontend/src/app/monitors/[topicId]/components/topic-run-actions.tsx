"use client";
import * as UI from "@/components/ui/content";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";

import { toast } from "sonner";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PlayIcon } from "lucide-react";

import { runMonitorTopic } from "@/api/jiankongzhuti";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { ApiRequestError } from "@/request";

type RunRequest = (
  topicId: string,
  input: HotKeyAPI.MonitorTopicRunInput,
) => Promise<HotKeyAPI.MonitorTopicRunView>;

export function createManualRunController(send: RunRequest) {
  let operationId: string | null = null;
  let sourceSignature: string | null = null;
  let inFlight: Promise<HotKeyAPI.MonitorTopicRunView> | null = null;
  let completed: HotKeyAPI.MonitorTopicRunView | null = null;

  return {
    run(topicId: string, sourceKeys: string[]) {
      const selected = [...sourceKeys].sort();
      const signature = `${topicId}:${selected.join(",")}`;
      if (selected.length === 0) {
        return Promise.reject(new Error("请至少选择一个来源。"));
      }
      if (sourceSignature !== signature) {
        operationId = null;
        completed = null;
        sourceSignature = signature;
      }
      if (completed) return Promise.resolve(completed);
      if (inFlight) return inFlight;
      operationId ??= crypto.randomUUID();
      inFlight = send(topicId, {
        operation_id: operationId,
        source_keys: selected as HotKeyAPI.SourceKeyInput[],
      })
        .then((result) => {
          completed = result;
          return result;
        })
        .finally(() => {
          inFlight = null;
        });
      return inFlight;
    },
    reset() {
      if (inFlight) return;
      operationId = null;
      completed = null;
      sourceSignature = null;
    },
  };
}

const SKIP_LABELS: Record<
  NonNullable<HotKeyAPI.MonitorTopicRunSourceView["skip_reason"]>,
  string
> = {
  source_unavailable: "来源待就绪",
  quiet: "当前处于静默时段",
  budget: "预算不足",
  rate_limited: "来源间隔尚未到期",
};

type Props = {
  topic: HotKeyAPI.MonitorTopicView;
  sourceNames: Record<string, string>;
  disabled?: boolean;
};

export function TopicRunResult({
  result,
  sourceNames,
}: {
  result: HotKeyAPI.MonitorTopicRunView;
  sourceNames: Record<string, string>;
}) {
  return (
    <UI.Content className="flex flex-col gap-3" role="status">
      <UI.Text size="sm">已按规则版本 v{result.topic_version} 处理</UI.Text>
      <ItemGroup className="flex flex-col gap-4">
        {result.sources.map((source) => (
          <Item
            role="listitem"
            variant="default"
            key={source.source_key}
            className="py-3 first:pt-0 last:pb-0"
          >
            <ItemContent className="min-w-0 gap-3">
              <UI.Text as="span" size="sm">
                {sourceNames[source.source_key] ?? source.source_key}
              </UI.Text>
              {source.skip_reason ? (
                <UI.Text as="span" tone="muted" size="sm">
                  {SKIP_LABELS[source.skip_reason]}
                </UI.Text>
              ) : (
                <UI.Text as="span" tone="muted" size="sm">
                  已受理 {source.job_ids.length} 个任务
                </UI.Text>
              )}
              {source.job_ids.map((jobId) => (
                <Button
                  asChild
                  variant="link"
                  className="self-start px-0"
                  key={jobId}
                >
                  <Link href={`/jobs/${jobId}`}>
                    查看任务 <UI.InlineCode>{jobId.slice(0, 8)}</UI.InlineCode>
                  </Link>
                </Button>
              ))}
            </ItemContent>
          </Item>
        ))}
      </ItemGroup>
    </UI.Content>
  );
}

export function TopicRunActions({
  topic,
  sourceNames,
  disabled = false,
}: Props) {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const [selected, setSelected] = useState<string[]>(topic.source_keys);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<HotKeyAPI.MonitorTopicRunView | null>(
    null,
  );
  const controller = useRef(
    createManualRunController((topicId, input) =>
      runMonitorTopic({ topic_id: topicId }, input),
    ),
  );

  function toggleSource(sourceKey: string) {
    setSelected((current) =>
      current.includes(sourceKey)
        ? current.filter((key) => key !== sourceKey)
        : [...current, sourceKey],
    );
    setResult(null);
    controller.current.reset();
  }

  async function submit() {
    if (pending || disabled || topic.status !== "active") return;
    setPending(true);
    try {
      const value = await controller.current.run(topic.id, selected);
      if (mounted.current) {
        setResult(value);
        toast.success("运行请求已处理，请核对各来源的受理结果。");
      }
    } catch (cause) {
      if (!mounted.current) return;
      if (cause instanceof ApiRequestError && cause.kind === "cancelled")
        return;
      if (cause instanceof ApiRequestError) {
        toast.error(
          cause.code === "topic_not_ready"
            ? "当前所选来源均未受理。请检查来源就绪状态、静默时段和预算。"
            : cause.code === "idempotency_conflict"
              ? "请求编号与先前的来源选择冲突，请重新选择后再试。"
              : cause.message,
          {
            description: cause.requestId
              ? `请求编号：${cause.requestId}`
              : undefined,
          },
        );
      } else {
        toast.error(
          cause instanceof Error ? cause.message : "采集请求失败，请重试。",
        );
      }
    } finally {
      if (mounted.current) setPending(false);
    }
  }

  return (
    <UI.Content
      as="section"
      aria-label="运行结果"
      className="flex flex-col gap-4"
    >
      <UI.Heading level={3}>最近一次手动运行</UI.Heading>
      <UI.Text tone="muted" size="sm">
        显示本页最近一次运行的真实受理结果。接口未提供分时命中数与主题自动运行历史；采集进度与保存条数可在任务详情查看。
      </UI.Text>
      {!result && (
        <UI.Text tone="muted" size="sm">
          本页尚无手动运行结果。
        </UI.Text>
      )}
      {topic.status !== "active" ? (
        <Alert className="mt-4" role="status">
          <AlertDescription>
            {topic.status === "paused"
              ? "主题已暂停，请先恢复。"
              : "已归档主题无法采集。"}
          </AlertDescription>
        </Alert>
      ) : topic.source_keys.length === 0 ? (
        <Alert className="mt-4" role="status">
          <AlertDescription>请先选择并保存来源。</AlertDescription>
        </Alert>
      ) : (
        <>
          <FieldSet
            className="mt-6"
            disabled={pending || disabled || result !== null}
          >
            <FieldLegend variant="label">本次来源</FieldLegend>
            <FieldGroup>
              {topic.source_keys.map((key) => (
                <Field
                  key={key}
                  orientation="horizontal"
                  data-disabled={pending || disabled || result !== null}
                >
                  <Switch
                    id={`run-source-${key}`}
                    checked={selected.includes(key)}
                    onCheckedChange={() => toggleSource(key)}
                    disabled={pending || disabled || result !== null}
                  />
                  <FieldLabel htmlFor={`run-source-${key}`}>
                    {sourceNames[key] ?? key}
                  </FieldLabel>
                </Field>
              ))}
            </FieldGroup>
          </FieldSet>
          {result ? (
            <UI.Content className="mt-6 flex flex-col gap-4">
              <TopicRunResult result={result} sourceNames={sourceNames} />
              <Button
                type="button"
                variant="outline"
                size="navigation"
                disabled={disabled}
                onClick={() => {
                  controller.current.reset();
                  setResult(null);
                }}
              >
                发起新一轮
              </Button>
            </UI.Content>
          ) : (
            <Button
              type="button"
              size="navigation"
              className="mt-6"
              disabled={pending || disabled || selected.length === 0}
              aria-busy={pending}
              onClick={() => void submit()}
            >
              {pending ? (
                <Spinner data-icon="inline-start" aria-hidden="true" />
              ) : (
                <PlayIcon data-icon="inline-start" />
              )}
              {pending ? "正在受理" : "立即采集"}
            </Button>
          )}
        </>
      )}
    </UI.Content>
  );
}
