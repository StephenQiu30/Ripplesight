import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  JobCoverageWindows,
  JobResult,
  JobSourceFreshness,
  JobTimingDetails,
} from "./job-detail";

describe("job timing", () => {
  it("separates queue, attempt, total and remaining cycle time", () => {
    const html = renderToStaticMarkup(
      createElement(JobTimingDetails, {
        job: {
          collection_cycle_no: 2,
          collection_cycle_started_at: "2026-09-27T12:03:00Z",
          collection_cycle_pending: false,
          collection_cycle_limit_seconds: 60,
          collection_cycle_remaining_us: 45_000_000,
          latest_attempt: {
            lease_epoch: 2,
            collection_cycle_no: 2,
            started_at: "2026-09-27T12:03:00Z",
            finished_at: null,
            outcome: null,
          },
          queue_wait_us: null,
          current_attempt_duration_us: 15_000_000,
          total_duration_us: 195_000_000,
        },
      }),
    );

    expect(html).toContain("排队等待</dt><dd");
    expect(html).toContain("当前尝试</dt><dd");
    expect(html).toContain("15 秒");
    expect(html).toContain("整单历时</dt><dd");
    expect(html).toContain("3 分钟 15 秒");
    expect(html).toContain("采集周期剩余</dt><dd");
    expect(html).toContain("45 秒");
    expect(html).toContain("第 2 个采集周期");
    expect(html).toContain("最近尝试 #2");
  });

  it("does not spend the next cycle while a manual retry waits", () => {
    const html = renderToStaticMarkup(
      createElement(JobTimingDetails, {
        job: {
          collection_cycle_no: 1,
          collection_cycle_started_at: "2026-09-27T12:00:00Z",
          collection_cycle_pending: true,
          collection_cycle_limit_seconds: 60,
          collection_cycle_remaining_us: null,
          latest_attempt: null,
          queue_wait_us: 60_000_000,
          current_attempt_duration_us: null,
          total_duration_us: 180_000_000,
        },
      }),
    );

    expect(html).toContain("1 分钟");
    expect(html).toContain("尚未开始");
    expect(html).toContain("下一周期将在领取任务时开始");
    expect(html).toContain("尚无执行尝试");
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
