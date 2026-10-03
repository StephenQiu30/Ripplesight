"use client";

import { toast } from "sonner";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  BanIcon,
  ChevronDownIcon,
  RefreshCwIcon,
  RotateCcwIcon,
} from "lucide-react";

import {
  cancelCollectionJob,
  getCollectionJob,
  retryCollectionJob,
} from "@/api/caijirenwu";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { PageState } from "@/components/system/page-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";
import { STATUS_LABELS, formatTime } from "../../components/job-presenters";

type JobDetailProps = {
  jobId: string;
};

type DetailState =
  | { status: "loading" }
  | { status: "ready"; job: HotKeyAPI.JobStatusView }
  | { status: "not-found" }
  | { status: "error"; message: string; requestId?: string };

const STAGE_LABELS: Record<HotKeyAPI.JobStage, string> = {
  request: "请求来源",
  parse: "解析响应",
  save: "保存结果",
  analysis: "分析内容",
};

const FAILURE_LABELS: Record<HotKeyAPI.JobFailureCategory, string> = {
  transient: "来源暂时不可用",
  rate_limited: "来源限流",
  authentication_required: "需要重新连接",
  permission_denied: "访问被拒绝",
  invalid_response: "来源响应无效",
  parse_error: "内容解析失败",
  invalid_input: "任务输入无效",
  configuration_unavailable: "配置不可用",
};

const DELAY_LABELS: Record<HotKeyAPI.JobDelayReason, string> = {
  internal_queue: "内部队列排队",
  rate_limited: "来源限流",
  budget_exhausted: "采集预算耗尽",
  transient_failure: "来源暂时不可用",
  manual_retry: "人工重试已排队",
  other: "其他延期",
};

const COVERAGE_STATUS_LABELS: Record<HotKeyAPI.CoverageWindowStatus, string> = {
  pending: "待执行",
  running: "采集中",
  confirmed: "已确认",
  partial: "部分完成",
};

const COVERAGE_STOP_REASON_LABELS: Record<string, string> = {
  access_denied: "访问被拒绝",
  authentication_required: "需要重新连接",
  budget_exhausted: "采集预算耗尽",
  cancelled: "任务被取消",
  cursor_expired: "分页游标失效",
  cursor_loop: "检测到重复分页",
  end_of_results: "已到结果末尾",
  not_found: "内容不可用",
  protocol_error: "来源响应无效",
  rate_limited: "来源限流",
  source_empty: "来源返回空结果",
  unverified_terminal: "结果终点未能验证",
  unsupported: "来源不支持此范围",
  upstream_error: "来源暂时不可用",
};

function toErrorState(
  error: unknown,
): Extract<DetailState, { status: "error" }> {
  if (error instanceof ApiRequestError) {
    return {
      status: "error",
      message: error.message,
      requestId: error.requestId,
    };
  }
  return { status: "error", message: "任务状态加载失败，请稍后重试。" };
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted-foreground text-sm">{label}</dt>
      <dd className="mt-1 text-base font-medium break-words">{value}</dd>
    </div>
  );
}

function formatDelayDuration(value: number | null): string {
  if (value === null) {
    return "时长暂不可用";
  }
  const seconds = Math.floor(value / 1_000_000);
  if (seconds === 0) {
    return "不足 1 秒";
  }
  if (seconds < 60) {
    return `${seconds} 秒`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    const remainingSeconds = seconds % 60;
    return `${minutes} 分钟${remainingSeconds ? ` ${remainingSeconds} 秒` : ""}`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    const remainingMinutes = minutes % 60;
    return `${hours} 小时${remainingMinutes ? ` ${remainingMinutes} 分钟` : ""}`;
  }
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return `${days} 天${remainingHours ? ` ${remainingHours} 小时` : ""}`;
}

export function JobSourceFreshness({
  freshness,
}: {
  freshness: HotKeyAPI.SourceFreshnessView;
}) {
  return (
    <section className="mt-8" aria-labelledby="source-freshness-title">
      <h2 id="source-freshness-title" className="text-xl font-medium">
        来源时效
      </h2>
      <div className="mt-6">
        <dl className="grid gap-x-8 gap-y-6 sm:grid-cols-2">
          <DetailItem
            label="最近尝试"
            value={
              freshness.last_attempt_at
                ? formatTime(freshness.last_attempt_at)
                : "尚无执行尝试"
            }
          />
          <DetailItem
            label="最近完整成功"
            value={
              freshness.last_success_at
                ? formatTime(freshness.last_success_at)
                : "尚无完整成功记录"
            }
          />
        </dl>
        {freshness.delay_reason ? (
          <p className="text-muted-foreground mt-5 text-sm leading-6">
            当前延期：{DELAY_LABELS[freshness.delay_reason]}，已等待{" "}
            {formatDelayDuration(freshness.delay_duration_us)}
            {freshness.delay_since_at
              ? `（自 ${formatTime(freshness.delay_since_at)}）`
              : ""}
            。
          </p>
        ) : null}
      </div>
    </section>
  );
}

export function JobCycleTiming({ job }: { job: HotKeyAPI.JobStatusView }) {
  const cyclePending = job.collection_cycle_pending;
  const active = job.status === "running" || job.status === "cancelling";
  const cycleLabel = cyclePending
    ? `第 ${job.collection_cycle_no + 1} 周期待领取`
    : job.collection_cycle_no > 0
      ? `第 ${job.collection_cycle_no} 周期`
      : "尚未开始";
  const cycleStarted = cyclePending
    ? "等待领取时开始"
    : job.collection_cycle_started_at
      ? formatTime(job.collection_cycle_started_at)
      : "尚未开始";
  const cycleRequests = cyclePending
    ? "新周期尚未开始"
    : job.collection_cycle_no === 0
      ? "尚未开始"
      : `${job.collection_cycle_requests_sent} 次`;
  const cycleRemaining = cyclePending
    ? "新周期尚未开始"
    : job.collection_cycle_no === 0
      ? "尚未开始"
      : job.collection_budget_remaining_us === null
        ? "暂无额度信息"
        : job.collection_budget_remaining_us === 0
          ? "已用完"
          : formatDelayDuration(job.collection_budget_remaining_us);
  const queueWait =
    job.queue_wait_us === null
      ? job.status === "queued"
        ? "等待领取"
        : "尚无记录"
      : formatDelayDuration(job.queue_wait_us);
  const attemptElapsed =
    job.attempt_elapsed_us === null
      ? job.latest_attempt_started_at
        ? "时长暂不可用"
        : "尚无尝试"
      : formatDelayDuration(job.attempt_elapsed_us);
  const totalElapsed =
    job.total_elapsed_us === null
      ? job.started_at
        ? "时长暂不可用"
        : "尚未开始"
      : formatDelayDuration(job.total_elapsed_us);

  return (
    <section className="mt-10" aria-labelledby="job-cycle-title">
      <h2 id="job-cycle-title" className="text-xl font-medium">
        任务时间与采集周期
      </h2>
      <div className="mt-6">
        <dl className="grid gap-x-8 gap-y-6 sm:grid-cols-2 xl:grid-cols-3">
          <DetailItem label="采集周期" value={cycleLabel} />
          <DetailItem label="周期开始" value={cycleStarted} />
          <DetailItem label="本周期已发请求" value={cycleRequests} />
          <DetailItem label="周期剩余额度" value={cycleRemaining} />
          <DetailItem label="排队等待" value={queueWait} />
          <DetailItem
            label={active ? "当前尝试历时" : "最近一次尝试历时"}
            value={attemptElapsed}
          />
          <DetailItem label="整单历时" value={totalElapsed} />
          <DetailItem
            label="最近一次尝试开始"
            value={
              job.latest_attempt_started_at
                ? formatTime(job.latest_attempt_started_at)
                : "尚无尝试"
            }
          />
          <DetailItem
            label="最近一次尝试结束"
            value={
              job.latest_attempt_finished_at
                ? formatTime(job.latest_attempt_finished_at)
                : active
                  ? "进行中"
                  : "尚无结束记录"
            }
          />
        </dl>
      </div>
    </section>
  );
}

export function JobResult({
  resultContentId,
  savedDescription,
  updatedAt,
}: {
  resultContentId: string | null;
  savedDescription: string;
  updatedAt: string | null;
}) {
  return (
    <section className="mt-10">
      <h2 className="text-xl font-medium">已写入结果</h2>
      <div className="mt-6">
        <p className="text-base font-medium">{savedDescription}</p>
        <p className="text-muted-foreground mt-2 text-sm leading-6">
          最后进度时间：{formatTime(updatedAt)}。
        </p>
        {resultContentId ? (
          <Button asChild className="mt-5">
            <Link href={`/content/${resultContentId}`}>
              打开作品资料
              <ArrowRightIcon data-icon="inline-end" />
            </Link>
          </Button>
        ) : (
          <p className="text-muted-foreground mt-3 text-sm leading-6">
            当前没有可打开的作品资料；失败或部分原因以上方持久状态为准。
          </p>
        )}
      </div>
    </section>
  );
}

export function JobCoverageWindows({
  windows,
}: {
  windows: HotKeyAPI.CoverageWindowView[];
}) {
  if (windows.length === 0) {
    return null;
  }

  return (
    <section className="mt-8" aria-labelledby="coverage-windows-title">
      <h2 id="coverage-windows-title" className="text-xl font-medium">
        采集窗口记录
      </h2>
      <p className="text-muted-foreground mt-2 text-sm leading-6">
        仅展示已保存窗口，不代表未记录范围已完整覆盖。
      </p>
      <ul className="mt-4 grid gap-3">
        {windows.map((window) => (
          <li
            key={window.id}
            className="flex flex-col items-start gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div>
              <p className="font-medium">
                {formatTime(window.starts_at)} — {formatTime(window.ends_at)}
              </p>
              <p className="text-muted-foreground mt-1 text-sm">
                {window.page_count} 页
                {window.stop_reason
                  ? ` · ${COVERAGE_STOP_REASON_LABELS[window.stop_reason] ?? "窗口尚未确认"}`
                  : ""}
              </p>
            </div>
            <Badge variant="secondary">
              {COVERAGE_STATUS_LABELS[window.status]}
            </Badge>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function JobDetail({ jobId }: JobDetailProps) {
  const [state, setState] = useState<DetailState>({ status: "loading" });
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isStale, setIsStale] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const request = useRef<AbortController | null>(null);
  const actionPending = useRef(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    request.current = controller;
    void getCollectionJob({ job_id: jobId }, { signal: controller.signal })
      .then((job) => {
        if (!controller.signal.aborted) {
          setState({ status: "ready", job });
          setIsStale(false);
        }
      })
      .catch((error: unknown) => {
        if (error instanceof ApiRequestError && error.kind === "cancelled")
          return;
        if (controller.signal.aborted) {
          return;
        }
        if (
          error instanceof ApiRequestError &&
          error.code === "resource_not_found"
        ) {
          setState({ status: "not-found" });
        } else {
          const failure = toErrorState(error);
          toast.error(failure.message, {
            description: failure.requestId
              ? `请求编号：${failure.requestId}`
              : undefined,
          });
          setState(failure);
        }
      });
    return () => {
      controller.abort();
      request.current?.abort();
    };
  }, [jobId, reloadToken]);

  async function refresh() {
    if (actionPending.current) return;
    actionPending.current = true;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setIsRefreshing(true);
    try {
      const job = await getCollectionJob(
        { job_id: jobId },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setState({ status: "ready", job });
      setIsStale(false);
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (controller.signal.aborted) return;
      setIsStale(true);
      toast.error(
        error instanceof ApiRequestError ? error.message : "刷新失败，请重试。",
        {
          description: [
            "当前显示上次读取的状态，请刷新后再核对。",
            error instanceof ApiRequestError && error.requestId
              ? `请求编号：${error.requestId}`
              : null,
          ]
            .filter(Boolean)
            .join(" "),
        },
      );
    } finally {
      actionPending.current = false;
      setIsRefreshing(false);
    }
  }

  async function cancel() {
    if (actionPending.current) return;
    actionPending.current = true;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setIsCancelling(true);
    try {
      const job = await cancelCollectionJob(
        { job_id: jobId },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setState({ status: "ready", job });
      setIsStale(false);
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (controller.signal.aborted) return;
      toast.error(
        error instanceof ApiRequestError ? error.message : "操作失败，请重试。",
        {
          description:
            error instanceof ApiRequestError && error.requestId
              ? `请求编号：${error.requestId}`
              : undefined,
        },
      );
    } finally {
      actionPending.current = false;
      setIsCancelling(false);
    }
  }

  async function retry() {
    if (actionPending.current) return;
    actionPending.current = true;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setIsRetrying(true);
    try {
      const job = await retryCollectionJob(
        { job_id: jobId },
        { signal: controller.signal },
      );
      if (controller.signal.aborted) return;
      setState({ status: "ready", job });
      setIsStale(false);
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      if (controller.signal.aborted) return;
      toast.error(
        error instanceof ApiRequestError ? error.message : "操作失败，请重试。",
        {
          description:
            error instanceof ApiRequestError && error.requestId
              ? `请求编号：${error.requestId}`
              : undefined,
        },
      );
    } finally {
      actionPending.current = false;
      setIsRetrying(false);
    }
  }

  if (state.status === "loading") {
    return (
      <PageState
        eyebrow="任务详情"
        title="正在读取任务"
        description="正在读取持久状态与已保存的结果范围。"
      />
    );
  }

  if (state.status === "not-found") {
    return (
      <PageState
        eyebrow="任务不可用"
        title="没有找到这个任务"
        description="任务不存在或已不可读。"
        action={
          <Button asChild variant="secondary">
            <Link href="/topics">
              <ArrowLeftIcon data-icon="inline-start" />
              返回工作台
            </Link>
          </Button>
        }
      />
    );
  }

  if (state.status === "error") {
    return (
      <PageState
        eyebrow="加载失败"
        title="暂时无法读取任务"
        description="请重新加载任务状态。"
        action={
          <Button
            type="button"
            onClick={() => {
              setState({ status: "loading" });
              setReloadToken((value) => value + 1);
            }}
          >
            <RotateCcwIcon data-icon="inline-start" />
            重新加载
          </Button>
        }
      />
    );
  }

  const { job } = state;
  const canCancel = job.status === "queued" || job.status === "running";
  const isCancellationPending = job.status === "cancelling";
  const savedDescription =
    job.progress.items_saved === 0
      ? "尚未保存结果；这不等于来源返回空结果。"
      : `已持久保存 ${job.progress.items_saved} 条结果。`;

  return (
    <div>
      <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-normal tracking-tight sm:text-4xl">
              采集任务
            </h1>
            <Badge
              variant={
                job.status === "failed" || job.cancellation?.timed_out
                  ? "destructive"
                  : "secondary"
              }
            >
              {STATUS_LABELS[job.status]}
            </Badge>
            {isStale ? <Badge variant="outline">状态待刷新</Badge> : null}
          </div>
          <p className="text-muted-foreground mt-3 text-sm">
            受理后在这里查看采集进度与结果。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => void refresh()}
            disabled={isRefreshing || isCancelling || isRetrying}
          >
            <RefreshCwIcon data-icon="inline-start" />
            {isRefreshing ? "正在刷新" : "刷新状态"}
          </Button>
          {canCancel ? (
            <Button
              type="button"
              variant="secondary"
              onClick={() => void cancel()}
              disabled={isRefreshing || isCancelling || isRetrying}
            >
              <BanIcon data-icon="inline-start" />
              {isCancelling ? "正在取消" : "取消任务"}
            </Button>
          ) : isCancellationPending ? (
            <Button type="button" variant="secondary" disabled>
              <BanIcon data-icon="inline-start" />
              等待在途请求
            </Button>
          ) : job.status === "failed" && job.failure?.manual_retry_allowed ? (
            <Button
              type="button"
              onClick={() => void retry()}
              disabled={isRefreshing || isCancelling || isRetrying}
            >
              <RotateCcwIcon data-icon="inline-start" />
              {isRetrying ? "正在提交" : "重试任务"}
            </Button>
          ) : null}
        </div>
      </div>

      {job.cancellation ? (
        <Alert
          variant={job.cancellation.timed_out ? "destructive" : "default"}
          className="mt-8"
          aria-live="polite"
        >
          <AlertTitle>
            {job.cancellation.timed_out ? "取消收尾已超时" : "已收到取消请求"}
          </AlertTitle>
          <AlertDescription>
            系统不会发起新的来源请求；已在途响应仍会按截止时间保存。
            {job.cancellation.deadline_at
              ? ` 截止时间：${formatTime(job.cancellation.deadline_at)}。`
              : " 当前任务无需等待在途请求。"}
          </AlertDescription>
        </Alert>
      ) : null}
      {job.failure ? (
        <Alert variant="destructive" className="mt-8" aria-live="polite">
          <AlertTitle>{FAILURE_LABELS[job.failure.category]}</AlertTitle>
          <AlertDescription>
            <p>
              {job.failure.next_action} 错误代码：{job.failure.error_code}。
            </p>
            <p>
              发生时间：{formatTime(job.failure.occurred_at)}。
              {job.next_run_at
                ? ` 下次尝试：${formatTime(job.next_run_at)}。`
                : " 当前没有自动重试计划。"}
            </p>
          </AlertDescription>
        </Alert>
      ) : null}

      <section
        className="mt-10 grid gap-4 sm:grid-cols-3"
        aria-label="任务进度"
      >
        <div className="py-4">
          <p className="text-muted-foreground text-sm">当前阶段</p>
          <p className="mt-2 text-xl font-medium">
            {job.progress.stage ? STAGE_LABELS[job.progress.stage] : "尚未开始"}
          </p>
        </div>
        <div className="py-4">
          <p className="text-muted-foreground text-sm">已发请求</p>
          <p className="mt-2 text-xl font-medium">
            {job.progress.requests_sent}
          </p>
        </div>
        <div className="py-4">
          <p className="text-muted-foreground text-sm">已保存结果</p>
          <p className="mt-2 text-xl font-medium">{job.progress.items_saved}</p>
        </div>
      </section>

      <JobResult
        resultContentId={job.result_content_id}
        savedDescription={savedDescription}
        updatedAt={job.progress.updated_at}
      />

      <Collapsible className="mt-10">
        <CollapsibleTrigger asChild>
          <Button variant="ghost">
            执行与覆盖记录
            <ChevronDownIcon data-icon="inline-end" />
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <JobCycleTiming job={job} />
          {job.source_freshness ? (
            <JobSourceFreshness freshness={job.source_freshness} />
          ) : null}

          <JobCoverageWindows windows={job.coverage_windows ?? []} />

          <section className="mt-10" aria-labelledby="job-facts-title">
            <h2 id="job-facts-title" className="text-xl font-medium">
              执行信息
            </h2>
            <dl className="mt-5 grid gap-x-8 gap-y-6 sm:grid-cols-2">
              <DetailItem label="任务编号" value={job.id} />
              <DetailItem
                label="配置"
                value={job.observation.configuration_ref}
              />
              <DetailItem
                label="配置版本"
                value={String(job.observation.configuration_version)}
              />
              <DetailItem label="任务类型" value={job.kind} />
              <DetailItem
                label="来源能力"
                value={job.observation.source_capability ?? "未指定"}
              />
              <DetailItem label="创建时间" value={formatTime(job.created_at)} />
              <DetailItem label="开始时间" value={formatTime(job.started_at)} />
              <DetailItem
                label="完成时间"
                value={formatTime(job.completed_at)}
              />
              <DetailItem
                label="计划时间"
                value={formatTime(job.scheduled_for_at)}
              />
              <DetailItem
                label="下次尝试"
                value={formatTime(job.next_run_at)}
              />
              <DetailItem label="重试次数" value={String(job.retry_count)} />
            </dl>
          </section>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
