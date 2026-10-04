"use client";

import { toast } from "sonner";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { ArrowRightIcon, RotateCcwIcon } from "lucide-react";

import { createMonitorTopic } from "@/api/jiankongzhuti";
import { listSourceCapabilities } from "@/api/laiyuannengli";
import { EditorialTopicSources } from "@/components/monitors/editorial-topic-sources";
import {
  KeywordGroupField,
  parseKeywordLines,
} from "@/components/monitors/keyword-group-field";
import { TopicRulePreview } from "@/components/monitors/topic-rule-preview";
import {
  selectableTopicSources,
  TopicAdvancedFields,
  TopicReportFields,
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
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const router = useRouter();
  const [sourcesState, setSourcesState] = useState<SourcesState>({
    status: "loading",
  });
  const [name, setName] = useState("");
  const [matchAny, setMatchAny] = useState("");
  const [matchAll, setMatchAll] = useState("");
  const [exclude, setExclude] = useState("");
  const [sourceKeys, setSourceKeys] = useState<string[]>([]);
  const [editorialProfileIds, setEditorialProfileIds] = useState<string[]>([]);
  const [collectionIntervalSeconds, setCollectionIntervalSeconds] =
    useState(3600);
  const [reportTime, setReportTime] = useState("08:00:00");
  const [weeklyReportEnabled, setWeeklyReportEnabled] = useState(true);
  const [notificationTargetNames, setNotificationTargetNames] = useState<
    string[]
  >([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [fieldErrors, setFieldErrors] = useState<TopicFieldErrors>({});
  const formRef = useRef<HTMLFormElement | null>(null);
  useEffect(() => {
    formRef.current?.querySelector<HTMLElement>("[aria-invalid=true]")?.focus();
  }, [fieldErrors]);

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
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (isCurrent) {
          const failure = toSourcesError(error);
          if (failure.status === "error")
            toast.error(failure.message, {
              description: failure.requestId
                ? `请求编号：${failure.requestId}`
                : undefined,
            });
          setSourcesState(failure);
        }
      });
    return () => {
      isCurrent = false;
    };
  }, []);

  async function reloadSources() {
    setSourcesState({ status: "loading" });
    try {
      const page = await listSourceCapabilities();
      if (!mounted.current) return;
      setSourcesState({
        status: "ready",
        sourceOptions: selectableTopicSources(page.items),
      });
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      const failure = toSourcesError(error);
      if (failure.status === "error")
        toast.error(failure.message, {
          description: failure.requestId
            ? `请求编号：${failure.requestId}`
            : undefined,
        });
      setSourcesState(failure);
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
    if (!reportTime) fields.report_time = "请选择每日报告时间。";
    if (
      !Number.isInteger(collectionIntervalSeconds) ||
      collectionIntervalSeconds < 600 ||
      collectionIntervalSeconds > 86400
    )
      fields.collection_interval_seconds = "请输入 600—86400 之间的整数秒。";
    if (Object.keys(fields).length) {
      setFieldErrors(fields);
      toast.error(Object.values(fields).join(" "));
      submittingRef.current = false;
      return;
    }
    setIsSubmitting(true);
    setFieldErrors({});
    try {
      const payload: HotKeyAPI.MonitorTopicCreateInput = {
        name: name.trim(),
        match_any: any,
        match_all: all,
        exclude: parseKeywordLines(exclude),
        source_keys: sourceKeys,
        editorial_profile_ids: editorialProfileIds,
        collection_interval_seconds: collectionIntervalSeconds,
        report_time: reportTime,
        weekly_report_enabled: weeklyReportEnabled,
        notification_target_names: notificationTargetNames,
      };
      const topic = await createMonitorTopic(payload);
      if (!mounted.current) return;
      router.replace(`/monitors/${topic.id}`);
      router.refresh();
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      const failure = toSubmissionError(error);
      setFieldErrors(failure.fields ?? {});
      toast.error(failure.message, {
        description:
          [
            ...Object.values(failure.fields ?? {}),
            failure.requestId ? `请求编号：${failure.requestId}` : null,
          ]
            .filter(Boolean)
            .join(" ") || undefined,
      });
    } finally {
      submittingRef.current = false;
      if (mounted.current) setIsSubmitting(false);
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
        <form
          ref={formRef}
          onSubmit={handleSubmit}
          noValidate
          aria-busy={isSubmitting}
        >
          <FieldGroup className="gap-8">
            <Field
              data-disabled={isSubmitting}
              data-invalid={Boolean(fieldErrors.name)}
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
                aria-invalid={Boolean(fieldErrors.name)}
                aria-describedby="topic-name-description"
              />
              <FieldDescription id="topic-name-description">
                起一个容易辨认的名字，之后可以随时修改。
              </FieldDescription>
            </Field>
            <KeywordGroupField
              id="match-any"
              label="想关注的关键词"
              description="任意一个词出现即可。每行填写一个，组合筛选可在进阶设置中调整。"
              value={matchAny}
              onChange={setMatchAny}
              disabled={isSubmitting}
              error={fieldErrors.match_any}
            />
            {sourcesState.status === "ready" ? (
              <TopicSettingsFields
                sourceOptions={sourcesState.sourceOptions}
                sourceKeys={sourceKeys}
                onSourceKeysChange={setSourceKeys}
                disabled={isSubmitting}
                fieldErrors={fieldErrors}
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
            <EditorialTopicSources
              selectedProfileIds={editorialProfileIds}
              onChange={setEditorialProfileIds}
              disabled={isSubmitting}
            />
            <TopicAdvancedFields
              matchAll={matchAll}
              onMatchAllChange={setMatchAll}
              exclude={exclude}
              onExcludeChange={setExclude}
              collectionIntervalSeconds={collectionIntervalSeconds}
              onCollectionIntervalSecondsChange={setCollectionIntervalSeconds}
              disabled={isSubmitting}
              fieldErrors={fieldErrors}
            />
            <TopicReportFields
              reportTime={reportTime}
              onReportTimeChange={setReportTime}
              weeklyReportEnabled={weeklyReportEnabled}
              onWeeklyReportEnabledChange={setWeeklyReportEnabled}
              notificationTargetNames={notificationTargetNames}
              onNotificationTargetNamesChange={setNotificationTargetNames}
              disabled={isSubmitting}
              error={fieldErrors.report_time}
            />
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
