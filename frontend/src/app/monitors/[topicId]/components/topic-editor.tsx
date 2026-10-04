"use client";

import { toast } from "sonner";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  ArchiveIcon,
  CopyIcon,
  PauseIcon,
  PlayIcon,
  RotateCcwIcon,
  SaveIcon,
} from "lucide-react";

import {
  archiveMonitorTopic,
  cloneMonitorTopic,
  getMonitorTopic,
  pauseMonitorTopic,
  resumeMonitorTopic,
  updateMonitorTopic,
} from "@/api/jiankongzhuti";
import { listSourceCapabilities } from "@/api/laiyuannengli";
import {
  KeywordGroupField,
  parseKeywordLines,
} from "@/components/monitors/keyword-group-field";
import { TopicRulePreview } from "@/components/monitors/topic-rule-preview";
import {
  selectableTopicSources,
  TopicSettingsFields,
  TopicAdvancedFields,
  TopicReportFields,
  type TopicSourceOption,
} from "@/components/monitors/topic-settings-fields";
import {
  readTopicFieldErrors,
  tryBeginTopicSubmission,
  type TopicFieldErrors,
} from "@/components/monitors/topic-validation";
import { PageState } from "@/components/system/page-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { ApiRequestError } from "@/request";

import { TopicRunActions } from "./topic-run-actions";

type TopicEditorProps = { topicId: string };

type EditorState =
  | { status: "loading" }
  | { status: "ready"; topic: HotKeyAPI.MonitorTopicView }
  | { status: "not-found" }
  | { status: "error"; message: string; requestId?: string };

type ActionFeedback = {
  kind: "error" | "conflict" | "success";
  message: string;
  requestId?: string;
  fields?: TopicFieldErrors;
};

type PendingAction = "archive" | "clone" | "pause" | "resume" | "save";

function toActionFeedback(error: unknown): ActionFeedback {
  if (error instanceof ApiRequestError) {
    if (error.code === "topic_version_conflict") {
      return {
        kind: "conflict",
        requestId: error.requestId,
        message: "这个主题已在其他页面更新。重新读取后再确认你的修改。",
      };
    }
    if (error.code === "keyword_group_conflict") {
      return {
        kind: "error",
        requestId: error.requestId,
        message: "同一个关键词不能同时放在包含组与排除组中。",
      };
    }
    if (error.code === "source_preset_not_applied") {
      return {
        kind: "error",
        requestId: error.requestId,
        message: "所选来源缺少已应用搜索预设、准入或启用的执行策略。",
      };
    }
    if (error.code === "topic_not_ready") {
      return {
        kind: "error",
        requestId: error.requestId,
        message: "来源或预算当前不可用，请在来源能力页核查后恢复。",
      };
    }
    return {
      kind: "error",
      message: error.message,
      requestId: error.requestId,
      fields: readTopicFieldErrors(error),
    };
  }
  return { kind: "error", message: "主题操作失败，请稍后重试。" };
}

export function TopicEditor({ topicId }: TopicEditorProps) {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const router = useRouter();
  const [state, setState] = useState<EditorState>({ status: "loading" });
  const [name, setName] = useState("");
  const [matchAny, setMatchAny] = useState("");
  const [matchAll, setMatchAll] = useState("");
  const [exclude, setExclude] = useState("");
  const [sourceOptions, setSourceOptions] = useState<TopicSourceOption[]>([]);
  const [sourceKeys, setSourceKeys] = useState<string[]>([]);
  const [collectionIntervalSeconds, setCollectionIntervalSeconds] =
    useState(1800);
  const [reportTime, setReportTime] = useState("09:00:00");
  const [weeklyReportEnabled, setWeeklyReportEnabled] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(
    null,
  );
  const pendingActionRef = useRef(false);
  const [fieldErrors, setFieldErrors] = useState<TopicFieldErrors>({});
  const formRef = useRef<HTMLFormElement | null>(null);
  useEffect(() => {
    formRef.current?.querySelector<HTMLElement>("[aria-invalid=true]")?.focus();
  }, [fieldErrors]);
  const isBusy = pendingAction !== null;

  const applyTopic = useCallback((value: HotKeyAPI.MonitorTopicView) => {
    setState({ status: "ready", topic: value });
    setName(value.name);
    setMatchAny(value.rules.match_any.join("\n"));
    setMatchAll(value.rules.match_all.join("\n"));
    setExclude(value.rules.exclude.join("\n"));
    setSourceKeys(value.source_keys);
    setCollectionIntervalSeconds(value.collection_interval_seconds);
    setReportTime(value.report_time);
    setWeeklyReportEnabled(value.weekly_report_enabled);
  }, []);

  const loadTopic = useCallback(async () => {
    setFieldErrors({});
    try {
      const [topic, sourcePage] = await Promise.all([
        getMonitorTopic({ topic_id: topicId }),
        listSourceCapabilities(),
      ]);
      if (!mounted.current) return;
      setSourceOptions(
        selectableTopicSources(sourcePage.items, topic.source_keys),
      );
      applyTopic(topic);
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (
        error instanceof ApiRequestError &&
        error.code === "resource_not_found"
      ) {
        setState({ status: "not-found" });
      } else if (error instanceof ApiRequestError) {
        toast.error(error.message, {
          description: error.requestId
            ? `请求编号：${error.requestId}`
            : undefined,
        });
        setState({
          status: "error",
          message: error.message,
          requestId: error.requestId,
        });
      } else {
        toast.error("主题加载失败，请稍后重试。");
        setState({ status: "error", message: "主题加载失败，请稍后重试。" });
      }
    }
  }, [applyTopic, topicId]);

  useEffect(() => {
    let isCurrent = true;
    void Promise.all([
      getMonitorTopic({ topic_id: topicId }),
      listSourceCapabilities(),
    ])
      .then(([topic, sourcePage]) => {
        if (isCurrent) {
          setSourceOptions(
            selectableTopicSources(sourcePage.items, topic.source_keys),
          );
          applyTopic(topic);
        }
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (!isCurrent) {
          return;
        }
        if (
          error instanceof ApiRequestError &&
          error.code === "resource_not_found"
        ) {
          setState({ status: "not-found" });
        } else if (error instanceof ApiRequestError) {
          toast.error(error.message, {
            description: error.requestId
              ? `请求编号：${error.requestId}`
              : undefined,
          });
          setState({
            status: "error",
            message: error.message,
            requestId: error.requestId,
          });
        } else {
          toast.error("主题加载失败，请稍后重试。");
          setState({
            status: "error",
            message: "主题加载失败，请稍后重试。",
          });
        }
      });
    return () => {
      isCurrent = false;
    };
  }, [applyTopic, topicId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      state.status !== "ready" ||
      !tryBeginTopicSubmission(pendingActionRef)
    ) {
      return;
    }
    const any = parseKeywordLines(matchAny);
    const all = parseKeywordLines(matchAll);
    if (!name.trim()) {
      setFieldErrors({ name: "请填写关注名称。" });
      toast.error("请填写关注名称。");
      pendingActionRef.current = false;
      return;
    }
    if (any.length === 0 && all.length === 0) {
      setFieldErrors({ match_any: "请填写至少一个关注关键词。" });
      toast.error("至少填写一个“任意命中”或“全部包含”关键词。");
      pendingActionRef.current = false;
      return;
    }
    if (!reportTime) {
      setFieldErrors({ report_time: "请选择每日报告时间。" });
      toast.error("请选择每日报告时间。");
      pendingActionRef.current = false;
      return;
    }
    if (
      !Number.isInteger(collectionIntervalSeconds) ||
      collectionIntervalSeconds < 600 ||
      collectionIntervalSeconds > 86400
    ) {
      setFieldErrors({
        collection_interval_seconds: "采集频率必须是 600—86400 之间的整数秒。",
      });
      toast.error("采集频率必须是 600—86400 之间的整数秒。");
      pendingActionRef.current = false;
      return;
    }

    setPendingAction("save");
    setFieldErrors({});
    try {
      const payload: HotKeyAPI.MonitorTopicUpdateInput = {
        name: name.trim(),
        match_any: any,
        match_all: all,
        exclude: parseKeywordLines(exclude),
        expected_version: state.topic.current_version,
        source_keys: sourceKeys,
        collection_interval_seconds: collectionIntervalSeconds,
        report_time: reportTime,
        weekly_report_enabled: weeklyReportEnabled,
        notification_target_names: state.topic.notification_target_names,
      };
      const topic = await updateMonitorTopic({ topic_id: topicId }, payload);
      if (!mounted.current) return;
      applyTopic(topic);
      toast.success(`已保存。当前规则版本为 v${topic.current_version}。`);
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      const failure = toActionFeedback(error);
      setFieldErrors(failure.fields ?? {});
      toast.error(failure.message, {
        description:
          [
            ...Object.values(failure.fields ?? {}),
            failure.requestId ? `请求编号：${failure.requestId}` : null,
          ]
            .filter(Boolean)
            .join(" ") || undefined,
        action:
          failure.kind === "conflict"
            ? { label: "重新读取", onClick: () => void loadTopic() }
            : undefined,
      });
    } finally {
      pendingActionRef.current = false;
      if (mounted.current) setPendingAction(null);
    }
  }

  async function runLifecycleAction(
    action: "archive" | "clone" | "pause" | "resume",
  ) {
    if (
      state.status !== "ready" ||
      !tryBeginTopicSubmission(pendingActionRef)
    ) {
      return;
    }
    setPendingAction(action);
    setFieldErrors({});
    try {
      if (action === "clone") {
        const clone = await cloneMonitorTopic({ topic_id: topicId });
        if (!mounted.current) return;
        router.push(`/monitors/${clone.id}`);
        return;
      }
      const operation =
        action === "archive"
          ? archiveMonitorTopic
          : action === "pause"
            ? pauseMonitorTopic
            : resumeMonitorTopic;
      const topic = await operation({ topic_id: topicId });
      if (!mounted.current) return;
      applyTopic(topic);
      toast.success(
        action === "archive"
          ? "主题已归档，规则历史仍会保留。"
          : action === "pause"
            ? "主题已暂停；正在运行的任务需在任务详情单独取消。"
            : "主题已恢复。",
      );
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      const failure = toActionFeedback(error);
      setFieldErrors(failure.fields ?? {});
      toast.error(failure.message, {
        description:
          [
            ...Object.values(failure.fields ?? {}),
            failure.requestId ? `请求编号：${failure.requestId}` : null,
          ]
            .filter(Boolean)
            .join(" ") || undefined,
        action:
          failure.kind === "conflict"
            ? { label: "重新读取", onClick: () => void loadTopic() }
            : undefined,
      });
    } finally {
      pendingActionRef.current = false;
      if (mounted.current) setPendingAction(null);
    }
  }

  if (state.status === "loading") {
    return (
      <PageState
        eyebrow="监控主题"
        title="正在读取主题"
        description="正在读取当前规则版本与持久状态。"
      />
    );
  }
  if (state.status === "not-found") {
    return (
      <PageState
        eyebrow="主题不可用"
        title="没有找到这个主题"
        description="主题不存在，或当前使用者无权查看。"
        action={
          <Button asChild variant="secondary">
            <Link href="/topics">返回工作台</Link>
          </Button>
        }
      />
    );
  }
  if (state.status === "error") {
    return (
      <PageState
        eyebrow="加载失败"
        title="暂时无法读取主题"
        description="请重新加载主题。"
        action={
          <Button type="button" onClick={() => void loadTopic()}>
            <RotateCcwIcon data-icon="inline-start" />
            重新加载
          </Button>
        }
      />
    );
  }

  const { topic } = state;
  const formDisabled = isBusy || topic.status === "archived";
  return (
    <div>
      <Button asChild variant="ghost" size="navigation" className="mb-10">
        <Link href="/topics">返回我的关注</Link>
      </Button>
      <div className="grid gap-12 md:grid-cols-2 md:gap-16">
        <section>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">
              {topic.status === "archived"
                ? "已归档"
                : topic.status === "active"
                  ? "运行中"
                  : "已暂停"}
            </Badge>
            <span className="text-muted-foreground text-sm">
              版本 v{topic.current_version}
            </span>
          </div>
          <h1 className="mt-5 text-4xl leading-tight font-normal tracking-tight sm:text-5xl">
            编辑关注
          </h1>
          <p className="text-muted-foreground mt-6 max-w-sm text-sm leading-7">
            调整关键词和来源，让关注更贴近你在意的事情。保存不会立即开始采集。
          </p>
          <div className="mt-8 flex flex-wrap gap-2">
            {topic.status === "active" ? (
              <Button
                type="button"
                variant="outline"
                size="navigation"
                disabled={isBusy}
                onClick={() => void runLifecycleAction("pause")}
              >
                <PauseIcon data-icon="inline-start" />
                暂停关注
              </Button>
            ) : topic.status === "paused" ? (
              <Button
                type="button"
                size="navigation"
                disabled={isBusy}
                onClick={() => void runLifecycleAction("resume")}
              >
                <PlayIcon data-icon="inline-start" />
                开始关注
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="navigation"
              disabled={isBusy}
              onClick={() => void runLifecycleAction("clone")}
            >
              <CopyIcon data-icon="inline-start" />
              复制
            </Button>
            {topic.status !== "archived" ? (
              <Button
                type="button"
                variant="ghost"
                size="navigation"
                disabled={isBusy}
                onClick={() => void runLifecycleAction("archive")}
              >
                <ArchiveIcon data-icon="inline-start" />
                归档
              </Button>
            ) : null}
          </div>
          <div className="mt-10">
            <TopicRunActions
              key={`${topic.id}:${topic.current_version}:${topic.source_keys.join(",")}`}
              topic={topic}
              sourceNames={Object.fromEntries(
                sourceOptions.map((source) => [
                  source.sourceKey,
                  source.displayName,
                ]),
              )}
              disabled={isBusy}
            />
          </div>
        </section>
        <form
          ref={formRef}
          onSubmit={handleSubmit}
          noValidate
          aria-busy={isBusy}
        >
          <FieldGroup className="gap-8">
            <Field
              data-disabled={formDisabled}
              data-invalid={Boolean(fieldErrors.name)}
            >
              <FieldLabel htmlFor="topic-name">主题名称</FieldLabel>
              <Input
                id="topic-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                disabled={formDisabled}
                minLength={1}
                maxLength={80}
                required
                aria-invalid={Boolean(fieldErrors.name)}
              />
            </Field>
            <KeywordGroupField
              id="match-any"
              label="想关注的关键词"
              description="任意一个词出现即可。每行填写一个关键词。"
              value={matchAny}
              onChange={setMatchAny}
              disabled={formDisabled}
              error={fieldErrors.match_any}
            />
            <TopicSettingsFields
              sourceOptions={sourceOptions}
              sourceKeys={sourceKeys}
              onSourceKeysChange={setSourceKeys}
              disabled={formDisabled}
              fieldErrors={fieldErrors}
            />
            <TopicAdvancedFields
              key={`${topic.id}:${topic.current_version}`}
              matchAll={matchAll}
              onMatchAllChange={setMatchAll}
              exclude={exclude}
              onExcludeChange={setExclude}
              collectionIntervalSeconds={collectionIntervalSeconds}
              onCollectionIntervalSecondsChange={setCollectionIntervalSeconds}
              disabled={formDisabled}
              fieldErrors={fieldErrors}
            />
            <TopicReportFields
              reportTime={reportTime}
              onReportTimeChange={setReportTime}
              weeklyReportEnabled={weeklyReportEnabled}
              onWeeklyReportEnabledChange={setWeeklyReportEnabled}
              disabled={formDisabled}
              error={fieldErrors.report_time}
            />
            <Field
              orientation="horizontal"
              className="flex-wrap justify-between gap-3"
              data-disabled={formDisabled}
            >
              <TopicRulePreview
                matchAny={matchAny}
                matchAll={matchAll}
                exclude={exclude}
                sourceKeys={sourceKeys}
                disabled={isBusy}
              />
              <Button type="submit" size="hero" disabled={formDisabled}>
                {pendingAction === "save" ? (
                  <Spinner data-icon="inline-start" aria-hidden="true" />
                ) : (
                  <SaveIcon data-icon="inline-start" />
                )}
                {pendingAction === "save" ? "正在保存" : "保存修改"}
              </Button>
            </Field>
            <FieldDescription>
              {topic.readiness_status === "pending_source_selection"
                ? "还未选择来源。保存后可以继续配置。"
                : topic.readiness_status === "pending_source_readiness"
                  ? "来源尚待就绪，请在来源设置中核查。"
                  : "开始关注前，会再次检查来源与预算。"}
            </FieldDescription>
          </FieldGroup>
        </form>
      </div>
    </div>
  );
}
