import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  JobCoverageWindows,
  JobCycleTiming,
  JobResult,
  JobSourceFreshness,
} from "./job-detail";

const baseJob = {
  id: "job-1",
  operation_id: "operation-1",
  kind: "source.hotlist",
  observation: {
    configuration_ref: "source:hotlist_weibo",
    configuration_version: 1,
    source_key: "hotlist_weibo",
    source_capability: "hotlist",
  },
  status: "queued",
  progress: {
    stage: null,
    requests_sent: 0,
    items_saved: 0,
    updated_at: null,
  },
  cancellation: null,
  failure: null,
  result_content_id: null,
  retry_count: 0,
  next_run_at: null,
  scheduled_for_at: null,
  started_at: null,
  completed_at: null,
  created_at: "2026-09-27T00:00:00Z",
  collection_cycle_no: 0,
  collection_cycle_started_at: null,
  collection_cycle_requests_sent: 0,
  collection_cycle_pending: false,
  latest_attempt_started_at: null,
  latest_attempt_finished_at: null,
  queue_wait_us: null,
  attempt_elapsed_us: null,
  total_elapsed_us: null,
  collection_budget_remaining_us: null,
} as HotKeyAPI.JobStatusView;

describe("job cycle timing", () => {
  it("keeps an unstarted job's time and budget unknown", () => {
    const html = renderToStaticMarkup(
      createElement(JobCycleTiming, { job: baseJob }),
    );

    expect(html).toContain("尚未开始");
    expect(html).toContain("等待领取");
    expect(html).not.toContain("45 秒");
  });

  it("shows queued manual retry without granting the next cycle's budget", () => {
    const html = renderToStaticMarkup(
      createElement(JobCycleTiming, {
        job: {
          ...baseJob,
          collection_cycle_no: 1,
          collection_cycle_started_at: "2026-09-27T00:01:00Z",
          collection_cycle_requests_sent: 1,
          collection_cycle_pending: true,
          latest_attempt_started_at: "2026-09-27T00:01:00Z",
          latest_attempt_finished_at: "2026-09-27T00:01:20Z",
          queue_wait_us: 60_000_000,
          attempt_elapsed_us: 20_000_000,
          total_elapsed_us: 180_000_000,
        },
      }),
    );

    expect(html).toContain("第 2 周期待领取");
    expect(html).toContain("等待领取时开始");
    expect(html).toContain("新周期尚未开始");
    expect(html).toContain("最近一次尝试历时");
    expect(html).toContain("20 秒");
    expect(html).not.toContain("45 秒");
  });

  it("separates queue wait, active attempt, whole job and cycle remainder", () => {
    const html = renderToStaticMarkup(
      createElement(JobCycleTiming, {
        job: {
          ...baseJob,
          status: "running",
          started_at: "2026-09-27T00:01:00Z",
          collection_cycle_no: 2,
          collection_cycle_started_at: "2026-09-27T00:04:00Z",
          collection_cycle_requests_sent: 1,
          latest_attempt_started_at: "2026-09-27T00:04:00Z",
          queue_wait_us: 180_000_000,
          attempt_elapsed_us: 12_000_000,
          total_elapsed_us: 300_000_000,
          collection_budget_remaining_us: 33_000_000,
        },
      }),
    );

    expect(html).toContain("第 2 周期");
    expect(html).toContain("本周期已发请求");
    expect(html).toContain("1 次");
    expect(html).toContain("排队等待");
    expect(html).toContain("3 分钟");
    expect(html).toContain("当前尝试历时");
    expect(html).toContain("12 秒");
    expect(html).toContain("整单历时");
    expect(html).toContain("5 分钟");
    expect(html).toContain("周期剩余额度");
    expect(html).toContain("33 秒");
  });

  it("labels the last finished attempt and exhausted budget on a terminal job", () => {
    const html = renderToStaticMarkup(
      createElement(JobCycleTiming, {
        job: {
          ...baseJob,
          status: "failed",
          started_at: "2026-09-27T00:01:00Z",
          completed_at: "2026-09-27T00:02:00Z",
          collection_cycle_no: 1,
          collection_cycle_started_at: "2026-09-27T00:01:00Z",
          collection_cycle_requests_sent: 1,
          latest_attempt_started_at: "2026-09-27T00:01:00Z",
          latest_attempt_finished_at: "2026-09-27T00:01:20Z",
          queue_wait_us: 60_000_000,
          attempt_elapsed_us: 20_000_000,
          total_elapsed_us: 120_000_000,
          collection_budget_remaining_us: 0,
        },
      }),
    );

    expect(html).toContain("最近一次尝试历时");
    expect(html).toContain("最近一次尝试结束");
    expect(html).toContain("2 分钟");
    expect(html).toContain("已用完");
  });
});

describe("job result", () => {
  it("links a persisted result to the existing content detail page", () => {
    const html = renderToStaticMarkup(
      createElement(JobResult, {
        resultContentId: "content-1",
        savedDescription: "已持久保存 1 条结果。",
        updatedAt: "2026-09-23T00:00:00Z",
      }),
    );

    expect(html).toContain('href="/content/content-1"');
    expect(html).toContain("打开作品资料");
    expect(html).not.toContain("当前没有可打开的作品资料");
  });

  it("keeps an honest state when no result is available", () => {
    const html = renderToStaticMarkup(
      createElement(JobResult, {
        resultContentId: null,
        savedDescription: "尚未保存结果；这不等于来源返回空结果。",
        updatedAt: "2026-09-23T00:00:00Z",
      }),
    );

    expect(html).toContain("当前没有可打开的作品资料");
    expect(html).not.toContain("打开作品资料");
  });
});

describe("job source freshness", () => {
  it("separates recent attempts from full success and labels budget delay", () => {
    const html = renderToStaticMarkup(
      createElement(JobSourceFreshness, {
        freshness: {
          last_attempt_at: "2026-09-24T11:55:00Z",
          last_success_at: "2026-09-24T10:00:00Z",
          delay_reason: "budget_exhausted",
          delay_since_at: "2026-09-24T11:58:30Z",
          delay_duration_us: 90_000_000,
        },
      }),
    );

    expect(html).toContain("最近尝试");
    expect(html).toContain("最近完整成功");
    expect(html).toContain("采集预算耗尽");
    expect(html).toContain("1 分钟 30 秒");
  });

  it("keeps absent history explicit without inventing a current delay", () => {
    const html = renderToStaticMarkup(
      createElement(JobSourceFreshness, {
        freshness: {
          last_attempt_at: null,
          last_success_at: null,
          delay_reason: null,
          delay_since_at: null,
          delay_duration_us: null,
        },
      }),
    );

    expect(html).toContain("尚无执行尝试");
    expect(html).toContain("尚无完整成功记录");
    expect(html).not.toContain("当前延期");
  });
});

describe("job coverage windows", () => {
  it("shows only persisted ranges without implying coverage beyond them", () => {
    const html = renderToStaticMarkup(
      createElement(JobCoverageWindows, {
        windows: [
          {
            id: "window-1",
            starts_at: "2026-09-21T00:00:00Z",
            ends_at: "2026-09-22T00:00:00Z",
            status: "partial",
            stop_reason: "cursor_loop",
            page_count: 2,
          },
        ],
      }),
    );

    expect(html).toContain("采集窗口记录");
    expect(html).toContain("部分完成");
    expect(html).toContain("检测到重复分页");
    expect(html).toContain("2 页");
    expect(html).toContain("不代表未记录范围已完整覆盖");
  });

  it("does not show an empty window block", () => {
    const html = renderToStaticMarkup(
      createElement(JobCoverageWindows, { windows: [] }),
    );

    expect(html).toBe("");
  });
});
