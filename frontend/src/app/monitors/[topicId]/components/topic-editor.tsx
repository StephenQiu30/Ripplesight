"use client";
import * as UI from "@/components/ui/content";

import { toast } from "sonner";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  type FormEvent,
  useCallback,
  useId,
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
import { EditorialTopicSources } from "@/components/monitors/editorial-topic-sources";
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
import {
  readMonitorFailure,
  topicStatusLabel,
  type MonitorFailure,
} from "@/components/monitors/monitor-presenters";
import { TopicAlerts } from "@/components/monitors/topic-alerts";
import { TopicOverview } from "./topic-overview";
import { PageState } from "@/components/system/page-state";
import { Button } from "@/components/ui/button";
import { MotionPanel } from "@/components/ui/motion-panel";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { ApiRequestError } from "@/request";

import { TopicResults } from "./topic-results";
import { TopicRunActions } from "./topic-run-actions";

type TopicEditorProps = {
  topicId: string;
  embedded?: boolean;
  onTopicChange?: (topic: HotKeyAPI.MonitorTopicView) => void;
};

type EditorState =
  | { status: "loading" }
  | { status: "ready"; topic: HotKeyAPI.MonitorTopicView }
  | { status: "not-found" }
  | ({ status: "error" } & MonitorFailure);

type ActionFeedback = {
  kind: "error" | "conflict" | "success";
  message: string;
  requestId?: string;
  fields?: TopicFieldErrors;
};

const TOPIC_TABS = [
  "overview",
  "results",
  "runs",
  "settings",
  "alerts",
] as const;
type TopicTab = (typeof TOPIC_TABS)[number];
function readTopicTab(): TopicTab {
  const value = new URLSearchParams(window.location.search).get("tab");
  return TOPIC_TABS.find((tab) => tab === value) ?? "overview";
}

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

export function TopicEditor({
  topicId,
  embedded = false,
  onTopicChange,
}: TopicEditorProps) {
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const router = useRouter();
  const controlsId = useId();
  const [activeTab, setActiveTab] = useState<TopicTab>("overview");
  useEffect(() => {
    const syncTab = () => setActiveTab(readTopicTab());
    syncTab();
    window.addEventListener("popstate", syncTab);
    return () => window.removeEventListener("popstate", syncTab);
  }, [topicId]);
  function selectTab(value: string) {
    const tab = TOPIC_TABS.find((item) => item === value) ?? "overview";
    setActiveTab(tab);
    const url = new URL(window.location.href);
    if (tab === "overview") url.searchParams.delete("tab");
    else url.searchParams.set("tab", tab);
    window.history.replaceState(window.history.state, "", url);
  }
  const [state, setState] = useState<EditorState>({ status: "loading" });
  const [reloadFailure, setReloadFailure] = useState<MonitorFailure | null>(
    null,
  );
  const [refreshing, setRefreshing] = useState(false);
  const [name, setName] = useState("");
  const [matchAny, setMatchAny] = useState("");
  const [matchAll, setMatchAll] = useState("");
  const [exclude, setExclude] = useState("");
  const [sourceOptions, setSourceOptions] = useState<TopicSourceOption[]>([]);
  const [sourceKeys, setSourceKeys] = useState<string[]>([]);
  const [editorialProfileIds, setEditorialProfileIds] = useState<string[]>([]);
  const [collectionIntervalSeconds, setCollectionIntervalSeconds] =
    useState(3600);
  const [reportTime, setReportTime] = useState("08:00:00");
  const [weeklyReportEnabled, setWeeklyReportEnabled] = useState(true);
  const [notificationTargetNames, setNotificationTargetNames] = useState<
    string[]
  >([]);
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

  const applyTopic = useCallback(
    (value: HotKeyAPI.MonitorTopicView) => {
      setState({ status: "ready", topic: value });
      setReloadFailure(null);
      onTopicChange?.(value);
      setName(value.name);
      setMatchAny(value.rules.match_any.join("\n"));
      setMatchAll(value.rules.match_all.join("\n"));
      setExclude(value.rules.exclude.join("\n"));
      setSourceKeys(value.source_keys);
      setEditorialProfileIds(value.editorial_profile_ids ?? []);
      setCollectionIntervalSeconds(value.collection_interval_seconds);
      setReportTime(value.report_time);
      setWeeklyReportEnabled(value.weekly_report_enabled);
      setNotificationTargetNames(value.notification_target_names);
    },
    [onTopicChange],
  );

  const loadTopic = useCallback(async () => {
    if (refreshing) return;
    setRefreshing(true);
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
        const failure = readMonitorFailure(error, "主题加载失败，请稍后重试。");
        if (state.status === "ready" && !failure.forbidden)
          setReloadFailure(failure);
        else setState({ status: "error", ...failure });
      } else {
        toast.error("主题加载失败，请稍后重试。");
        const failure = readMonitorFailure(error, "主题加载失败，请稍后重试。");
        if (state.status === "ready") setReloadFailure(failure);
        else setState({ status: "error", ...failure });
      }
    } finally {
      if (mounted.current) setRefreshing(false);
    }
  }, [applyTopic, topicId, state, refreshing]);

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
            ...readMonitorFailure(error, "主题加载失败，请稍后重试。"),
          });
        } else {
          toast.error("主题加载失败，请稍后重试。");
          setState({
            status: "error",
            ...readMonitorFailure(error, "主题加载失败，请稍后重试。"),
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
        editorial_profile_ids: editorialProfileIds,
        collection_interval_seconds: collectionIntervalSeconds,
        report_time: reportTime,
        weekly_report_enabled: weeklyReportEnabled,
        notification_target_names: notificationTargetNames,
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
      <>
        {!embedded && (
          <UI.Heading level={1} className="sr-only">
            正在读取主题
          </UI.Heading>
        )}
        <PageState
          headingLevel={embedded ? 2 : 1}
          state="loading"
          loadingLayout="detail"
          eyebrow="监控主题"
          title="正在读取主题"
          description="正在读取当前规则版本与持久状态。"
        />
      </>
    );
  }
  if (state.status === "not-found") {
    return (
      <PageState
        headingLevel={embedded ? 2 : 1}
        state="empty"
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
        headingLevel={embedded ? 2 : 1}
        state={state.forbidden ? "forbidden" : "error"}
        eyebrow="加载失败"
        title={state.forbidden ? "无权读取监控主题" : "暂时无法读取主题"}
        description={
          state.forbidden
            ? "请登录有权访问这个主题的账户。"
            : "请重新加载主题。"
        }
        errorCode={state.code}
        httpStatus={state.httpStatus}
        action={
          state.forbidden ? undefined : (
            <Button
              type="button"
              disabled={refreshing}
              aria-busy={refreshing}
              onClick={() => void loadTopic()}
            >
              <RotateCcwIcon data-icon="inline-start" />
              重新加载
            </Button>
          )
        }
      />
    );
  }

  const { topic } = state;
  const formDisabled = isBusy || topic.status === "archived";
  return (
    <UI.Content className="flex min-w-0 flex-col gap-8">
      {reloadFailure && (
        <PageState
          headingLevel={2}
          state="stale"
          eyebrow="监控主题"
          title="主题刷新失败"
          description="已显示的规则已过期；当前草稿会保留，请重新读取后再保存。"
          errorCode={reloadFailure.code}
          httpStatus={reloadFailure.httpStatus}
          staleAt={topic.updated_at}
          action={
            <Button
              type="button"
              variant="outline"
              disabled={refreshing}
              onClick={() => void loadTopic()}
            >
              重新读取
            </Button>
          }
        />
      )}
      {!embedded && (
        <Button
          asChild
          variant="ghost"
          size="navigation"
          className="self-start"
        >
          <Link href="/topics">返回我的关注</Link>
        </Button>
      )}
      <UI.Content className="flex min-w-0 flex-col gap-8">
        <UI.Content
          as="section"
          aria-label="主题详情"
          className="flex flex-col gap-5"
        >
          <UI.Heading
            level={embedded ? 2 : 1}
            appearance={embedded ? "form" : undefined}
          >
            {topic.name}
          </UI.Heading>
          <UI.Text tone="muted" size="xs">
            {topicStatusLabel(topic.status)} · 每{" "}
            {topic.collection_interval_seconds / 60} 分钟检索 ·{" "}
            {topic.source_keys.length} 个来源
          </UI.Text>
        </UI.Content>
        <TopicOverview
          topic={topic}
          sources={sourceOptions}
          onSourceChange={(key, checked) => {
            setSourceKeys((current) =>
              checked
                ? [...new Set([...current, key])]
                : current.filter((value) => value !== key),
            );
            selectTab("settings");
          }}
        />
        <TopicAlerts topicId={topic.id} />
        <UI.Content
          className="flex flex-wrap gap-2 border-t pt-6"
          role="group"
          aria-label="主题操作"
        >
          <Button
            variant="secondary"
            id={`${controlsId}-results-trigger`}
            aria-controls={`${controlsId}-results-panel`}
            aria-expanded={activeTab === "results"}
            onClick={() =>
              selectTab(activeTab === "results" ? "overview" : "results")
            }
          >
            查看监控结果
          </Button>
          <Button
            variant="secondary"
            id={`${controlsId}-runs-trigger`}
            aria-controls={`${controlsId}-runs-panel`}
            aria-expanded={activeTab === "runs"}
            onClick={() =>
              selectTab(activeTab === "runs" ? "overview" : "runs")
            }
          >
            采集与运行
          </Button>
          <Button
            variant="secondary"
            id={`${controlsId}-settings-trigger`}
            aria-controls={`${controlsId}-settings-panel`}
            aria-expanded={activeTab === "settings"}
            onClick={() =>
              selectTab(activeTab === "settings" ? "overview" : "settings")
            }
          >
            编辑主题设置
          </Button>
        </UI.Content>
        <UI.Content className="min-w-0">
          <MotionPanel
            open={activeTab === "results"}
            id={`${controlsId}-results-panel`}
            aria-labelledby={`${controlsId}-results-trigger`}
            triggerId={`${controlsId}-results-trigger`}
            className="min-w-0"
          >
            <TopicResults topicId={topic.id} />
          </MotionPanel>
          <MotionPanel
            open={activeTab === "settings"}
            id={`${controlsId}-settings-panel`}
            aria-labelledby={`${controlsId}-settings-trigger`}
            triggerId={`${controlsId}-settings-trigger`}
            className="min-w-0"
          >
            <UI.Content className="flex flex-col gap-6">
              <UI.Content
                className="grid grid-cols-1 gap-4 sm:grid-cols-2"
                aria-label="已保存关键词"
              >
                {(
                  [
                    ["任一关键词", topic.rules.match_any],
                    ["全部关键词", topic.rules.match_all],
                    ["排除关键词", topic.rules.exclude],
                  ] as const
                ).map(([label, words]) => (
                  <UI.Content
                    key={label}
                    className="flex min-w-0 flex-col gap-2"
                  >
                    <UI.Text tone="muted" size="xs">
                      {label}
                    </UI.Text>
                    <UI.Text size="sm" className="break-words">
                      {words.join(" · ") || "未设置"}
                    </UI.Text>
                  </UI.Content>
                ))}
              </UI.Content>
              <UI.Text tone="muted" size="sm">
                调整后保存才会生效，保存不会立即开始采集。
              </UI.Text>
              <UI.Content className="flex flex-wrap gap-2">
                {topic.status === "active" ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="navigation"
                    disabled={isBusy}
                    aria-busy={pendingAction === "pause"}
                    onClick={() => void runLifecycleAction("pause")}
                  >
                    {pendingAction === "pause" ? (
                      <Spinner aria-hidden="true" data-icon="inline-start" />
                    ) : (
                      <PauseIcon data-icon="inline-start" />
                    )}
                    暂停关注
                  </Button>
                ) : topic.status === "paused" ? (
                  <Button
                    type="button"
                    size="navigation"
                    disabled={isBusy}
                    aria-busy={pendingAction === "resume"}
                    onClick={() => void runLifecycleAction("resume")}
                  >
                    {pendingAction === "resume" ? (
                      <Spinner aria-hidden="true" data-icon="inline-start" />
                    ) : (
                      <PlayIcon data-icon="inline-start" />
                    )}
                    恢复关注
                  </Button>
                ) : null}
                <Button
                  type="button"
                  variant="ghost"
                  size="navigation"
                  disabled={isBusy}
                  aria-busy={pendingAction === "clone"}
                  onClick={() => void runLifecycleAction("clone")}
                >
                  {pendingAction === "clone" ? (
                    <Spinner aria-hidden="true" data-icon="inline-start" />
                  ) : (
                    <CopyIcon data-icon="inline-start" />
                  )}
                  复制
                </Button>
                {topic.status !== "archived" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="navigation"
                    disabled={isBusy}
                    aria-busy={pendingAction === "archive"}
                    onClick={() => void runLifecycleAction("archive")}
                  >
                    {pendingAction === "archive" ? (
                      <Spinner aria-hidden="true" data-icon="inline-start" />
                    ) : (
                      <ArchiveIcon data-icon="inline-start" />
                    )}
                    归档
                  </Button>
                ) : null}
              </UI.Content>
              <UI.Form
                aria-label="编辑主题设置"
                ref={formRef}
                onSubmit={handleSubmit}
                noValidate
              >
                <FieldGroup className="gap-6">
                  <UI.Heading level={3}>主题设置</UI.Heading>
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
                  <EditorialTopicSources
                    selectedProfileIds={editorialProfileIds}
                    onChange={setEditorialProfileIds}
                    disabled={formDisabled}
                  />
                  <TopicAdvancedFields
                    key={`${topic.id}:${topic.current_version}`}
                    matchAll={matchAll}
                    onMatchAllChange={setMatchAll}
                    exclude={exclude}
                    onExcludeChange={setExclude}
                    collectionIntervalSeconds={collectionIntervalSeconds}
                    onCollectionIntervalSecondsChange={
                      setCollectionIntervalSeconds
                    }
                    disabled={formDisabled}
                    fieldErrors={fieldErrors}
                  />
                  <TopicReportFields
                    reportTime={reportTime}
                    onReportTimeChange={setReportTime}
                    weeklyReportEnabled={weeklyReportEnabled}
                    onWeeklyReportEnabledChange={setWeeklyReportEnabled}
                    notificationTargetNames={notificationTargetNames}
                    onNotificationTargetNamesChange={setNotificationTargetNames}
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
                    <Button
                      type="submit"
                      size="navigation"
                      disabled={formDisabled}
                      aria-busy={pendingAction === "save"}
                    >
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
              </UI.Form>
            </UI.Content>
          </MotionPanel>
          <MotionPanel
            open={activeTab === "runs"}
            id={`${controlsId}-runs-panel`}
            aria-labelledby={`${controlsId}-runs-trigger`}
            triggerId={`${controlsId}-runs-trigger`}
            className="min-w-0"
          >
            <UI.Content>
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
            </UI.Content>
          </MotionPanel>
        </UI.Content>
      </UI.Content>
    </UI.Content>
  );
}
