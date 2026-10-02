"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  getCodexResetConfiguration,
  getCodexResetSnapshot,
  getCodexResetVersion,
  getRecentCodexResets,
} from "@/api/zhongzhigonggao";
import { PageState } from "@/components/system/page-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ApiRequestError } from "@/request";
import { ResetCalendar } from "./reset-calendar";
import { ResetSourcePosts } from "./reset-source-posts";
import { beijingTime, ResetTimeline } from "./reset-timeline";

type Reading = {
  configuration: HotKeyAPI.MonitorView;
  snapshot: HotKeyAPI.ResetSnapshot;
  recent: HotKeyAPI.ResetSnapshot;
};
type State =
  | { status: "loading" }
  | { status: "unconfigured" }
  | { status: "error"; message: string }
  | { status: "ready"; data: Reading; refreshing?: boolean; warning?: string };
const healthLabel: Record<HotKeyAPI.ResetHealth["status"], string> = {
  unknown: "暂无完整核验",
  attention: "需要关注",
  delayed: "解释或扫描有延迟",
  healthy: "最近核验正常",
};

function errorMessage(error: unknown) {
  return error instanceof ApiRequestError
    ? `${error.message}${error.requestId ? ` 请求编号：${error.requestId}` : ""}`
    : "公告读取失败，请稍后重试。";
}

export function CodexResetWorkspace() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [refresh, setRefresh] = useState(0);
  const [range, setRange] = useState<"all" | "recent">("all");
  const [includeWithdrawn, setIncludeWithdrawn] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const version = state.status === "ready" ? state.data.snapshot.version : null;
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      getCodexResetConfiguration({ signal: controller.signal }),
      getCodexResetSnapshot(
        { include_withdrawn: includeWithdrawn },
        { signal: controller.signal },
      ),
      getRecentCodexResets({ signal: controller.signal }),
    ])
      .then(([configuration, snapshot, recent]) => {
        if (controller.signal.aborted) return;
        if (!configuration) {
          setState({ status: "unconfigured" });
          return;
        }
        if (!snapshot || !recent)
          throw new Error("inconsistent monitor snapshot");
        setState({
          status: "ready",
          data: { configuration, snapshot, recent },
        });
      })
      .catch((error) => {
        if (
          controller.signal.aborted ||
          (error instanceof ApiRequestError && error.kind === "cancelled")
        )
          return;
        setState((previous) =>
          previous.status === "ready"
            ? {
                ...previous,
                refreshing: false,
                warning: `刷新失败，仍显示上次读取的数据。${errorMessage(error)}`,
              }
            : { status: "error", message: errorMessage(error) },
        );
      });
    return () => controller.abort();
  }, [refresh, includeWithdrawn]);

  useEffect(() => {
    if (!version) return;
    const controller = new AbortController();
    const timer = setInterval(() => {
      if (document.visibilityState === "hidden") return;
      void getCodexResetVersion({ signal: controller.signal })
        .then((probe) => {
          if (!controller.signal.aborted && probe?.version !== version)
            setRefresh((value) => value + 1);
        })
        .catch((error) => {
          if (
            !controller.signal.aborted &&
            !(error instanceof ApiRequestError && error.kind === "cancelled")
          )
            setState((previous) =>
              previous.status === "ready"
                ? {
                    ...previous,
                    warning: `版本检查失败，当前为上次读取的数据。${errorMessage(error)}`,
                  }
                : previous,
            );
        });
    }, 60_000);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [version]);

  function reload() {
    setState((previous) =>
      previous.status === "ready"
        ? { ...previous, refreshing: true, warning: undefined }
        : { status: "loading" },
    );
    setRefresh((value) => value + 1);
  }
  if (state.status === "loading")
    return (
      <div>
        <h1 className="text-3xl font-medium">Codex 重置公告</h1>
        <p role="status" className="text-muted-foreground mt-6">
          正在读取公告与日历…
        </p>
      </div>
    );
  if (state.status === "error")
    return (
      <PageState
        eyebrow="公告读取"
        title="暂时无法读取公告"
        description={state.message}
        action={<Button onClick={reload}>重试读取公告</Button>}
      />
    );
  if (state.status === "unconfigured")
    return (
      <PageState
        eyebrow="Codex 重置公告"
        title="尚未配置公告监控"
        description="公告监控需要维护者配置官方 X 来源并确认凭据、本人授权与预算。当前没有公告记录。"
        action={
          <div className="flex flex-wrap gap-3">
            <Button variant="outline" onClick={reload}>
              刷新公告
            </Button>
            <Button asChild>
              <Link href="/codex-resets/manage">配置与人工复核</Link>
            </Button>
          </div>
        }
      />
    );
  const { snapshot, recent, configuration } = state.data;
  const active = range === "recent" ? recent : snapshot;
  const selectedIds = new Set(
    active.calendar
      .filter((mark) => mark.date === selectedDate)
      .map((mark) => mark.event_id),
  );
  const events = selectedDate
    ? active.events.filter((event) => selectedIds.has(event.id))
    : active.events;
  const health = snapshot.monitor;
  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
            Codex 重置公告
          </h1>
          <p className="text-muted-foreground mt-4 max-w-2xl leading-7">
            从源公告阅读重置、重置额度与确认进展。时间估计和推测始终保留未确认状态。
          </p>
          <Link
            href="/codex-resets/manage"
            className="mt-3 inline-block text-sm underline underline-offset-4"
          >
            配置与人工复核
          </Link>
        </div>
        <Button variant="outline" onClick={reload} disabled={state.refreshing}>
          {state.refreshing ? "正在刷新…" : "刷新公告"}
        </Button>
      </div>
      {state.warning && (
        <p role="alert" className="text-destructive mt-6 text-sm leading-6">
          {state.warning}
        </p>
      )}
      {!configuration.enabled && (
        <p role="status" className="bg-secondary mt-6 rounded-xl p-4 text-sm">
          监控已关闭。下方保留已有记录，暂无新扫描或识别。
        </p>
      )}
      <section aria-label="公告监控健康" className="mt-10 space-y-5">
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">
            {configuration.enabled ? healthLabel[health.status] : "监控已关闭"}
          </Badge>
          <Badge variant="outline">待处理 {health.pending_count}</Badge>
          <Badge variant="outline">待复核 {health.review_count}</Badge>
          <Badge variant="outline">采集缺口 {health.held_window_count}</Badge>
        </div>
        <dl className="text-muted-foreground grid gap-4 text-sm sm:grid-cols-3">
          {[
            ["最近尝试", health.last_attempt_at],
            ["最近采集", health.last_collected_at],
            ["最近完整核验", health.last_verified_at],
          ].map(([label, time]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd className="text-foreground mt-1">{beijingTime(time)}</dd>
            </div>
          ))}
        </dl>
        <dl className="grid grid-cols-2 gap-5 py-4 sm:grid-cols-4">
          {[
            ["90 日直接重置", snapshot.statistics.resets_90],
            ["90 日重置额度", snapshot.statistics.credits_90],
            [
              "重置中位间隔",
              snapshot.statistics.median_interval_days == null
                ? "暂无记录"
                : `${snapshot.statistics.median_interval_days.toFixed(1)} 天`,
            ],
            ["上次确认日期", snapshot.statistics.last_reset_date ?? "暂无记录"],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-muted-foreground text-sm">{label}</dt>
              <dd className="mt-2 text-2xl font-medium">{value}</dd>
            </div>
          ))}
        </dl>
      </section>
      <div className="mt-8 grid items-start gap-10 lg:grid-cols-2">
        <ResetCalendar
          snapshot={snapshot}
          selectedDate={selectedDate}
          onSelect={setSelectedDate}
        />
        <div>
          <div className="mb-7 flex flex-wrap items-center gap-3">
            <Button
              variant={range === "all" ? "secondary" : "ghost"}
              aria-pressed={range === "all"}
              onClick={() => {
                setRange("all");
                setSelectedDate(null);
              }}
            >
              完整记录
            </Button>
            <Button
              variant={range === "recent" ? "secondary" : "ghost"}
              aria-pressed={range === "recent"}
              onClick={() => {
                setRange("recent");
                setSelectedDate(null);
              }}
            >
              最近七日
            </Button>
            <label className="text-muted-foreground flex items-center gap-2 text-sm">
              <Checkbox
                checked={includeWithdrawn}
                disabled={range === "recent"}
                onCheckedChange={(value) => setIncludeWithdrawn(value === true)}
              />
              包含已撤回
            </label>
          </div>
          {selectedDate && (
            <p className="text-muted-foreground mb-5 text-sm">
              {selectedDate} 的公告
            </p>
          )}
          <ResetTimeline events={events} outage={active.outage} />
        </div>
      </div>
      <ResetSourcePosts refresh={refresh} />
    </div>
  );
}
