"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { LoaderCircleIcon, PlayIcon } from "lucide-react";

import { runMonitorTopic } from "@/api/jiankongzhuti";
import { Button } from "@/components/ui/button";
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
    <div className="space-y-3" role="status">
      <p className="text-sm font-medium">
        已按规则版本 v{result.topic_version} 处理
      </p>
      <ul className="divide-border divide-y text-sm">
        {result.sources.map((source) => (
          <li key={source.source_key} className="py-3 first:pt-0 last:pb-0">
            <span className="font-medium">
              {sourceNames[source.source_key] ?? source.source_key}
            </span>
            {source.skip_reason ? (
              <span className="text-muted-foreground ml-2">
                {SKIP_LABELS[source.skip_reason]}
              </span>
            ) : (
              <span className="text-muted-foreground ml-2">
                已受理 {source.job_ids.length} 个任务
              </span>
            )}
            {source.job_ids.map((jobId) => (
              <Link
                key={jobId}
                href={`/jobs/${jobId}`}
                className="text-primary mt-2 block underline-offset-4 hover:underline"
              >
                查看任务 {jobId.slice(0, 8)}
              </Link>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TopicRunActions({
  topic,
  sourceNames,
  disabled = false,
}: Props) {
  const router = useRouter();
  const [selected, setSelected] = useState<string[]>(topic.source_keys);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<HotKeyAPI.MonitorTopicRunView | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
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
    setError(null);
    controller.current.reset();
  }

  async function submit() {
    if (pending || disabled || topic.status !== "active") return;
    setPending(true);
    setError(null);
    try {
      setResult(await controller.current.run(topic.id, selected));
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.status === 401) {
        router.replace("/login");
        return;
      }
      if (cause instanceof ApiRequestError) {
        setError(
          cause.code === "topic_not_ready"
            ? "当前所选来源均未受理。请检查来源就绪状态、静默时段和预算。"
            : cause.code === "idempotency_conflict"
              ? "请求编号与先前的来源选择冲突，请重新选择后再试。"
              : cause.message,
        );
      } else {
        setError(
          cause instanceof Error ? cause.message : "采集请求失败，请重试。",
        );
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <section
      className="bg-muted mt-4 rounded-2xl p-5"
      aria-labelledby="topic-run-title"
    >
      <h2 id="topic-run-title" className="text-sm font-medium">
        手动采集
      </h2>
      <p className="text-muted-foreground mt-2 text-sm leading-5">
        按当前已保存的规则版本发起一次采集。结果会列出每个来源的任务或跳过原因。
      </p>
      {topic.status !== "active" ? (
        <p className="mt-4 text-sm" role="status">
          {topic.status === "paused"
            ? "主题已暂停，请先恢复。"
            : "已归档主题无法采集。"}
        </p>
      ) : topic.source_keys.length === 0 ? (
        <p className="mt-4 text-sm" role="status">
          请先选择并保存来源。
        </p>
      ) : (
        <>
          <fieldset
            className="mt-4 space-y-2"
            disabled={pending || disabled || result !== null}
          >
            <legend className="text-sm font-medium">本次来源</legend>
            {topic.source_keys.map((sourceKey) => (
              <label
                key={sourceKey}
                className="flex min-h-10 items-center gap-2 text-sm"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(sourceKey)}
                  onChange={() => toggleSource(sourceKey)}
                  className="accent-primary size-4"
                />
                {sourceNames[sourceKey] ?? sourceKey}
              </label>
            ))}
          </fieldset>
          {result ? (
            <div className="mt-4 space-y-3">
              <TopicRunResult result={result} sourceNames={sourceNames} />
              <Button
                type="button"
                variant="secondary"
                className="w-full"
                onClick={() => {
                  controller.current.reset();
                  setResult(null);
                }}
              >
                发起新一轮
              </Button>
            </div>
          ) : (
            <Button
              type="button"
              className="mt-4 w-full"
              disabled={pending || disabled || selected.length === 0}
              onClick={() => void submit()}
            >
              {pending ? (
                <LoaderCircleIcon
                  className="animate-spin motion-reduce:animate-none"
                  aria-hidden="true"
                />
              ) : (
                <PlayIcon data-icon="inline-start" aria-hidden="true" />
              )}
              {pending ? "正在受理" : "立即采集"}
            </Button>
          )}
          {error ? (
            <p role="alert" className="text-destructive mt-3 text-sm">
              {error}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
