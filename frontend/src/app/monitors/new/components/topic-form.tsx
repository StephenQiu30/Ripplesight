"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { ArrowRightIcon, RotateCcwIcon } from "lucide-react";

import { createMonitorTopic } from "@/api/jiankongzhuti";
import { listSourceCapabilities } from "@/api/laiyuannengli";
import {
  KeywordGroupField,
  parseKeywordLines,
} from "@/components/monitors/keyword-group-field";
import { TopicRulePreview } from "@/components/monitors/topic-rule-preview";
import {
  selectableTopicSources,
  TopicAdvancedFields,
  TopicSettingsFields,
  type TopicSourceOption,
} from "@/components/monitors/topic-settings-fields";
import {
  readTopicFieldErrors,
  tryBeginTopicSubmission,
  type TopicFieldErrors,
} from "@/components/monitors/topic-validation";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { ApiRequestError } from "@/request";

type SubmissionError = {
  message: string;
  requestId?: string;
  fields?: TopicFieldErrors;
};
type SourcesState =
  | { status: "loading" }
  | { status: "ready"; sourceOptions: TopicSourceOption[] }
  | { status: "error"; message: string; requestId?: string };

function toSubmissionError(error: unknown): SubmissionError {
  if (!(error instanceof ApiRequestError))
    return { message: "关注保存失败，请稍后重试。" };
  const message =
    error.code === "keyword_group_conflict"
      ? "同一个关键词不能同时放在包含组与排除组中。"
      : error.code === "invalid_monitor_rules"
        ? "至少填写一个“任意命中”或“全部包含”关键词。"
        : error.code === "source_preset_not_applied"
          ? "所选来源缺少已应用搜索预设、准入或启用的执行策略。"
          : error.message;
  return {
    message,
    requestId: error.requestId,
    fields: readTopicFieldErrors(error),
  };
}

function toSourcesError(error: unknown): SourcesState {
  return {
    status: "error",
    message:
      error instanceof ApiRequestError
        ? error.message
        : "来源配置加载失败，请稍后重试。",
    requestId: error instanceof ApiRequestError ? error.requestId : undefined,
  };
}

export function TopicForm() {
  const router = useRouter();
  const [sourcesState, setSourcesState] = useState<SourcesState>({
    status: "loading",
  });
  const [name, setName] = useState("");
  const [matchAny, setMatchAny] = useState("");
  const [matchAll, setMatchAll] = useState("");
  const [exclude, setExclude] = useState("");
  const [sourceKeys, setSourceKeys] = useState<string[]>([]);
  const [collectionIntervalSeconds, setCollectionIntervalSeconds] =
    useState(1800);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [submissionError, setSubmissionError] =
    useState<SubmissionError | null>(null);

  useEffect(() => {
    let isCurrent = true;
    void listSourceCapabilities()
      .then((page) => {
        if (isCurrent)
          setSourcesState({
            status: "ready",
            sourceOptions: selectableTopicSources(page.items),
          });
      })
      .catch((error: unknown) => {
        if (isCurrent) setSourcesState(toSourcesError(error));
      });
    return () => {
      isCurrent = false;
    };
  }, []);

  async function reloadSources() {
    setSourcesState({ status: "loading" });
    try {
      const page = await listSourceCapabilities();
      setSourcesState({
        status: "ready",
        sourceOptions: selectableTopicSources(page.items),
      });
    } catch (error) {
      setSourcesState(toSourcesError(error));
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!tryBeginTopicSubmission(submittingRef)) return;
    const any = parseKeywordLines(matchAny);
    const all = parseKeywordLines(matchAll);
    const fields: TopicFieldErrors = {};
    if (!name.trim()) fields.name = "请填写关注名称。";
    if (!any.length && !all.length)
      fields.match_any = "至少填写一个包含关键词。";
    if (
      !Number.isInteger(collectionIntervalSeconds) ||
      collectionIntervalSeconds < 600 ||
      collectionIntervalSeconds > 86400
    )
      fields.collection_interval_seconds = "请输入 600—86400 之间的整数秒。";
    if (Object.keys(fields).length) {
      setSubmissionError({ message: "请检查填写的内容。", fields });
      submittingRef.current = false;
      return;
    }
    setIsSubmitting(true);
    setSubmissionError(null);
    try {
      const payload: HotKeyAPI.MonitorTopicCreateInput = {
        name: name.trim(),
        match_any: any,
        match_all: all,
        exclude: parseKeywordLines(exclude),
        source_keys: sourceKeys,
        collection_interval_seconds: collectionIntervalSeconds,
      };
      const topic = await createMonitorTopic(payload);
      router.replace(`/monitors/${topic.id}`);
      router.refresh();
    } catch (error) {
      setSubmissionError(toSubmissionError(error));
    } finally {
      submittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  return (
    <div>
      <Button asChild variant="ghost" size="navigation" className="mb-10">
        <Link href="/topics">返回我的关注</Link>
      </Button>
      <div className="grid gap-12 md:grid-cols-2 md:gap-16">
        <section>
          <p className="text-muted-foreground text-sm">创建关注</p>
          <h1 className="mt-5 text-4xl leading-tight font-normal tracking-tight sm:text-5xl">
            从你关心的
            <br />
            事情开始。
          </h1>
          <p className="text-muted-foreground mt-6 max-w-sm text-sm leading-7">
            选好关键词和信息来源，以适合自己的节奏了解新的变化。
          </p>
        </section>
        <form onSubmit={handleSubmit} noValidate aria-busy={isSubmitting}>
          <FieldGroup className="gap-8">
            <Field
              data-disabled={isSubmitting}
              data-invalid={Boolean(submissionError?.fields?.name)}
            >
              <FieldLabel htmlFor="topic-name">主题名称</FieldLabel>
              <Input
                id="topic-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                disabled={isSubmitting}
                minLength={1}
                maxLength={80}
                required
                placeholder="例如：AI 产品与工具"
                aria-invalid={Boolean(submissionError?.fields?.name)}
                aria-describedby={
                  submissionError?.fields?.name
                    ? "topic-name-error"
                    : "topic-name-description"
                }
              />
              {submissionError?.fields?.name ? (
                <FieldError id="topic-name-error">
                  {submissionError.fields.name}
                </FieldError>
              ) : (
                <FieldDescription id="topic-name-description">
                  起一个容易辨认的名字，之后可以随时修改。
                </FieldDescription>
              )}
            </Field>
            <KeywordGroupField
              id="match-any"
              label="想关注的关键词"
              description="任意一个词出现即可。每行填写一个，组合筛选可在进阶设置中调整。"
              value={matchAny}
              onChange={setMatchAny}
              disabled={isSubmitting}
              error={submissionError?.fields?.match_any}
            />
            {sourcesState.status === "ready" ? (
              <TopicSettingsFields
                sourceOptions={sourcesState.sourceOptions}
                sourceKeys={sourceKeys}
                onSourceKeysChange={setSourceKeys}
                disabled={isSubmitting}
                fieldErrors={submissionError?.fields}
              />
            ) : sourcesState.status === "loading" ? (
              <Field>
                <FieldLabel>信息来源</FieldLabel>
                <FieldDescription>
                  正在读取来源配置。你可以先填写关键词。
                </FieldDescription>
                <Spinner aria-label="正在读取来源" />
              </Field>
            ) : (
              <Alert variant="destructive">
                <AlertTitle>信息来源暂时不可用</AlertTitle>
                <AlertDescription>
                  {sourcesState.message}
                  {sourcesState.requestId ? (
                    <p>请求编号：{sourcesState.requestId}</p>
                  ) : null}
                  <p>可以先保存关注，之后再配置来源。</p>
                </AlertDescription>
                <Button
                  type="button"
                  variant="outline"
                  size="navigation"
                  disabled={isSubmitting}
                  onClick={() => void reloadSources()}
                >
                  <RotateCcwIcon data-icon="inline-start" />
                  重新读取来源
                </Button>
              </Alert>
            )}
            <TopicAdvancedFields
              matchAll={matchAll}
              onMatchAllChange={setMatchAll}
              exclude={exclude}
              onExcludeChange={setExclude}
              collectionIntervalSeconds={collectionIntervalSeconds}
              onCollectionIntervalSecondsChange={setCollectionIntervalSeconds}
              disabled={isSubmitting}
              fieldErrors={submissionError?.fields}
            />
            {submissionError ? (
              <Alert variant="destructive">
                <AlertTitle>无法保存关注</AlertTitle>
                <AlertDescription>
                  {submissionError.message}
                  {submissionError.requestId ? (
                    <p>请求编号：{submissionError.requestId}</p>
                  ) : null}
                </AlertDescription>
              </Alert>
            ) : null}
            <Field
              orientation="horizontal"
              className="flex-wrap justify-between gap-3"
            >
              <TopicRulePreview
                matchAny={matchAny}
                matchAll={matchAll}
                exclude={exclude}
                sourceKeys={sourceKeys}
                disabled={isSubmitting}
              />
              <Button type="submit" size="hero" disabled={isSubmitting}>
                {isSubmitting ? (
                  <Spinner data-icon="inline-start" aria-hidden="true" />
                ) : null}
                {isSubmitting ? "正在保存" : "保存关注"}
                <ArrowRightIcon data-icon="inline-end" />
              </Button>
            </Field>
            <FieldDescription>
              保存后保持暂停。准备好后可在关注详情开始运行。
            </FieldDescription>
          </FieldGroup>
        </form>
      </div>
    </div>
  );
}
