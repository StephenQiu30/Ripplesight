"use client";
import * as UI from "@/components/ui/content";

import { Spinner } from "@/components/ui/spinner";
import { Item, ItemContent, ItemDescription } from "@/components/ui/item";
import { FieldLabel, Field } from "@/components/ui/field";
import { Alert, AlertDescription } from "@/components/ui/alert";

import { useId, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
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
  | { status: "error"; forbidden?: boolean }
  | { status: "ready"; data: Reading; refreshing?: boolean; stale?: boolean };
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
  const fieldId = useId();

  const [state, setState] = useState<State>({ status: "loading" });
  const [refresh, setRefresh] = useState(0);
  const [range, setRange] = useState<"all" | "recent">("all");
  const [includeWithdrawn, setIncludeWithdrawn] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const versionProbeFailed = useRef(false);
  const permissionVersion = useRef(0);
  const version = state.status === "ready" ? state.data.snapshot.version : null;
  useEffect(() => {
    const controller = new AbortController();
    const readVersion = permissionVersion.current;
    void Promise.all([
      getCodexResetConfiguration({ signal: controller.signal }),
      getCodexResetSnapshot(
        { include_withdrawn: includeWithdrawn },
        { signal: controller.signal },
      ),
      getRecentCodexResets({ signal: controller.signal }),
    ])
      .then(([configuration, snapshot, recent]) => {
        if (
          controller.signal.aborted ||
          readVersion !== permissionVersion.current
        )
          return;
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
        versionProbeFailed.current = false;
      })
      .catch((error) => {
        if (
          controller.signal.aborted ||
          readVersion !== permissionVersion.current ||
          (error instanceof ApiRequestError && error.kind === "cancelled")
        )
          return;
        toast.error(errorMessage(error));
        if (
          error instanceof ApiRequestError &&
          (error.status === 401 || error.status === 403)
        ) {
          permissionVersion.current += 1;
          setState({ status: "error", forbidden: true });
          return;
        }
        setState((previous) =>
          previous.status === "ready"
            ? {
                ...previous,
                refreshing: false,
                stale: true,
              }
            : { status: "error" },
        );
      });
    return () => controller.abort();
  }, [refresh, includeWithdrawn]);

  useEffect(() => {
    if (!version) return;
    const controller = new AbortController();
    const timer = setInterval(() => {
      if (document.visibilityState === "hidden") return;
      const readVersion = permissionVersion.current;
      void getCodexResetVersion({ signal: controller.signal })
        .then((probe) => {
          if (
            controller.signal.aborted ||
            readVersion !== permissionVersion.current
          )
            return;
          versionProbeFailed.current = false;
          if (!controller.signal.aborted && probe?.version !== version)
            setRefresh((value) => value + 1);
        })
        .catch((error) => {
          if (
            !controller.signal.aborted &&
            readVersion === permissionVersion.current &&
            !(error instanceof ApiRequestError && error.kind === "cancelled")
          ) {
            if (!versionProbeFailed.current) toast.error(errorMessage(error));
            versionProbeFailed.current = true;
            if (
              error instanceof ApiRequestError &&
              (error.status === 401 || error.status === 403)
            ) {
              permissionVersion.current += 1;
              setState({ status: "error", forbidden: true });
              return;
            }
            setState((previous) =>
              previous.status === "ready"
                ? {
                    ...previous,
                    stale: true,
                  }
                : previous,
            );
          }
        });
    }, 60_000);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [version]);

  function reload() {
    permissionVersion.current += 1;
    setState((previous) =>
      previous.status === "ready"
        ? { ...previous, refreshing: true, stale: undefined }
        : { status: "loading" },
    );
    setRefresh((value) => value + 1);
  }
  if (state.status === "loading")
    return (
      <UI.Content>
        <UI.Heading level={1} className="text-3xl font-medium">
          Codex 重置公告
        </UI.Heading>
        <Item role="status" className="mt-6">
          <Spinner aria-hidden="true" />
          <ItemContent>
            <ItemDescription className="line-clamp-none">
              正在读取公告与日历…
            </ItemDescription>
          </ItemContent>
        </Item>
      </UI.Content>
    );
  if (state.status === "error")
    return (
      <PageState
        state={state.forbidden ? "forbidden" : "error"}
        eyebrow="公告读取"
        title={state.forbidden ? "无权读取公告" : "暂时无法读取公告"}
        description="可以重新读取公告与日历。"
        action={<Button onClick={reload}>重试读取公告</Button>}
      />
    );
  if (state.status === "unconfigured")
    return (
      <PageState
        state="empty"
        eyebrow="Codex 重置公告"
        title="尚未配置公告监控"
        description="公告监控需要维护者配置官方 X 来源并确认凭据、本人授权与预算。当前没有公告记录。"
        action={
          <UI.Content className="flex flex-wrap gap-3">
            <Button variant="outline" onClick={reload}>
              刷新公告
            </Button>
            <Button asChild>
              <Link href="/codex-resets/manage">配置与人工复核</Link>
            </Button>
          </UI.Content>
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
    <UI.Content>
      <UI.Content className="flex flex-wrap items-end justify-between gap-5">
        <UI.Content>
          <UI.Heading
            level={1}
            className="text-3xl font-medium tracking-tight sm:text-4xl"
          >
            Codex 重置公告
          </UI.Heading>
          <UI.Text className="text-muted-foreground mt-4 max-w-2xl leading-7">
            从源公告阅读重置、重置额度与确认进展。时间估计和推测始终保留未确认状态。
          </UI.Text>
          <Link
            href="/codex-resets/manage"
            className="mt-3 inline-block text-sm underline underline-offset-4"
          >
            配置与人工复核
          </Link>
        </UI.Content>
        <Button variant="outline" onClick={reload} disabled={state.refreshing}>
          {state.refreshing ? "正在刷新…" : "刷新公告"}
        </Button>
      </UI.Content>
      {state.stale && (
        <Alert className="mt-6">
          <AlertDescription>
            当前为上次读取的数据，刷新后可以检查最新公告。
          </AlertDescription>
        </Alert>
      )}
      {!configuration.enabled && (
        <Alert role="status" className="mt-6 p-4">
          <AlertDescription>
            监控已关闭。下方保留已有记录，暂无新扫描或识别。
          </AlertDescription>
        </Alert>
      )}
      <UI.Content
        as="section"
        aria-label="公告监控健康"
        className="mt-10 flex flex-col gap-y-5"
      >
        <UI.Content className="flex flex-wrap gap-2">
          <Badge variant="secondary">
            {configuration.enabled ? healthLabel[health.status] : "监控已关闭"}
          </Badge>
          <Badge variant="outline">待处理 {health.pending_count}</Badge>
          <Badge variant="outline">待复核 {health.review_count}</Badge>
          <Badge variant="outline">采集缺口 {health.held_window_count}</Badge>
        </UI.Content>
        <UI.Content
          as="dl"
          className="text-muted-foreground grid gap-4 text-sm sm:grid-cols-3"
        >
          {[
            ["最近尝试", health.last_attempt_at],
            ["最近采集", health.last_collected_at],
            ["最近完整核验", health.last_verified_at],
          ].map(([label, time]) => (
            <UI.Content key={label}>
              <UI.Content as="dt">{label}</UI.Content>
              <UI.Content as="dd" className="text-foreground mt-1">
                {beijingTime(time)}
              </UI.Content>
            </UI.Content>
          ))}
        </UI.Content>
        <UI.Content
          as="dl"
          className="grid grid-cols-2 gap-5 py-4 sm:grid-cols-4"
        >
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
            <UI.Content key={label}>
              <UI.Content as="dt" className="text-muted-foreground text-sm">
                {label}
              </UI.Content>
              <UI.Content as="dd" className="mt-2 text-2xl font-medium">
                {value}
              </UI.Content>
            </UI.Content>
          ))}
        </UI.Content>
      </UI.Content>
      <UI.Content className="mt-8 grid items-start gap-10 lg:grid-cols-2">
        <ResetCalendar
          snapshot={snapshot}
          selectedDate={selectedDate}
          onSelect={setSelectedDate}
        />
        <UI.Content>
          <UI.Content className="mb-7 flex flex-wrap items-center gap-3">
            <ToggleGroup
              type="single"
              value={range}
              aria-label="公告日期范围"
              onValueChange={(value) => {
                if (!value) return;
                setRange(value as typeof range);
                setSelectedDate(null);
              }}
            >
              <ToggleGroupItem value="all">完整记录</ToggleGroupItem>
              <ToggleGroupItem value="recent">最近七日</ToggleGroupItem>
            </ToggleGroup>
            <Field
              orientation="horizontal"
              className="w-auto"
              data-disabled={range === "recent"}
            >
              <Checkbox
                checked={includeWithdrawn}
                disabled={range === "recent"}
                onCheckedChange={(value) => setIncludeWithdrawn(value === true)}
                id={`${fieldId}-codex-reset-workspace-field-1`}
              />
              <FieldLabel htmlFor={`${fieldId}-codex-reset-workspace-field-1`}>
                包含已撤回
              </FieldLabel>
            </Field>
          </UI.Content>
          {selectedDate && (
            <UI.Text className="text-muted-foreground mb-5 text-sm">
              {selectedDate} 的公告
            </UI.Text>
          )}
          <ResetTimeline events={events} outage={active.outage} />
        </UI.Content>
      </UI.Content>
      <ResetSourcePosts refresh={refresh} />
    </UI.Content>
  );
}
