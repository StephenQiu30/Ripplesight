import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/caijifugai", () => ({
  getCollectionCoverage: vi.fn(),
  getCollectionCoverageMetrics: vi.fn(),
  listCollectionCoverage: vi.fn(),
}));

import { listCollectionCoverage } from "@/api/caijifugai";

import { CoverageWindowDetail } from "./coverage-window-detail";
import { CoverageWindowTable } from "./coverage-window-table";
import {
  coverageQueryFromDraft,
  coverageUrl,
  parseCoverageQuery,
  readCoveragePage,
  shanghaiLocalToUtc,
  utcToShanghaiLocal,
  windowMatchesQuery,
} from "./source-coverage-panel";

const query = {
  start: "2026-09-27T00:00:00.000Z",
  end: "2026-09-28T00:00:00.000Z",
  sourceKey: "hotlist_weibo",
  capability: "hotlist" as const,
};

const windowRow: HotKeyAPI.CollectionCoverageView = {
  window_id: "window-1",
  source_key: "hotlist_weibo",
  capability: "hotlist",
  topic_id: null,
  due_at: "2026-09-27T11:00:00Z",
  window_start: "2026-09-27T10:30:00Z",
  window_end: "2026-09-27T11:00:00Z",
  admission_state: "missed",
  admission_reason: "budget",
  current_connection_version: 3,
  job_connection_version: null,
  job_id: null,
  job_status: null,
  attempts: null,
  started_at: null,
  finished_at: null,
  last_success_at: null,
  coverage_status: "not_attempted",
  terminal_evidence: null,
  stop_reason: "budget_exhausted",
  request_count: null,
  request_attempt_count: null,
  page_count: 0,
  observed_count: null,
  inserted_count: 0,
  deduplicated_count: null,
  analysis: null,
  budgets: null,
  gaps: [
    {
      starts_at: "2026-09-27T10:30:00Z",
      ends_at: "2026-09-27T11:00:00Z",
      reason: "budget_exhausted",
    },
  ],
  content_ids: null,
  snapshot_ids: null,
};

describe("coverage filters", () => {
  it("interprets local input in Asia/Shanghai and preserves a UTC half-open range", () => {
    expect(shanghaiLocalToUtc("2026-09-28T08:00")).toBe(
      "2026-09-28T00:00:00.000Z",
    );
    expect(utcToShanghaiLocal("2026-09-28T00:00:00Z")).toBe("2026-09-28T08:00");
    expect(shanghaiLocalToUtc("2026-02-30T08:00")).toBeNull();
    expect(
      coverageQueryFromDraft({
        sourceKey: "hotlist_weibo",
        capability: "hotlist",
        startLocal: "2026-09-27T08:00",
        endLocal: "2026-09-28T08:00",
      }).query,
    ).toEqual(query);
  });

  it("rejects overlong, reversed and timezone-free URL ranges", () => {
    const raw = new URLSearchParams({ start: query.start, end: query.end });
    expect(parseCoverageQuery(raw)).toEqual({
      ...query,
      sourceKey: "",
      capability: "",
    });
    raw.set("end", "2026-10-29T00:00:01Z");
    expect(parseCoverageQuery(raw)).toBeNull();
    raw.set("end", "2026-09-26T00:00:00Z");
    expect(parseCoverageQuery(raw)).toBeNull();
    raw.set("end", "2026-09-28T00:00:00");
    expect(parseCoverageQuery(raw)).toBeNull();
  });

  it("writes filters to URL and drops the selected window when filters change", () => {
    const selected = coverageUrl(query, "window-1");
    expect(selected).toContain("window=window-1");
    expect(coverageUrl({ ...query, sourceKey: "hackernews" })).not.toContain(
      "window=",
    );
    expect(
      parseCoverageQuery(new URLSearchParams(selected.split("?")[1])),
    ).toEqual(query);
  });
});

describe("coverage facts", () => {
  it("rejects a detail window outside the current source, capability or time range", () => {
    expect(windowMatchesQuery(windowRow, query)).toBe(true);
    expect(
      windowMatchesQuery(windowRow, { ...query, sourceKey: "hackernews" }),
    ).toBe(false);
    expect(
      windowMatchesQuery(windowRow, { ...query, capability: "search" }),
    ).toBe(false);
    expect(
      windowMatchesQuery(windowRow, {
        ...query,
        end: "2026-09-27T11:00:00.000Z",
      }),
    ).toBe(false);
  });

  it("keeps no-Job missed windows visible and distinguishes unknown from zero", () => {
    const list = renderToStaticMarkup(
      createElement(CoverageWindowTable, {
        items: [windowRow],
        selectedId: null,
        onSelect: vi.fn(),
      }),
    );
    expect(list).toContain("错过到期");
    expect(list).toContain("未尝试");
    expect(list).toContain("1 段未确认缺口");
    expect(list).toContain("未知");
    expect(list).toContain("0");

    const detail = renderToStaticMarkup(
      createElement(CoverageWindowDetail, { row: windowRow, onClose: vi.fn() }),
    );
    expect(detail).toContain("这个到期窗口没有关联 Job");
    expect(detail).toContain("当前连接版本");
    expect(detail).toContain("v3");
    expect(detail).toContain("Job 固定连接版本");
    expect(detail).toContain("budget_exhausted");
    expect(detail).not.toContain("/jobs/null");
  });

  it("links a recorded Job, content and fixed hotlist snapshot", () => {
    const detail = renderToStaticMarkup(
      createElement(CoverageWindowDetail, {
        row: {
          ...windowRow,
          job_id: "job-1",
          job_status: "succeeded",
          job_connection_version: 2,
          content_ids: ["content-1"],
          snapshot_ids: ["snapshot-1"],
        },
        onClose: vi.fn(),
      }),
    );
    expect(detail).toContain('href="/jobs/job-1"');
    expect(detail).toContain('href="/content/content-1"');
    expect(detail).toContain("snapshot=snapshot-1");
    expect(detail).toContain("v2");
  });

  it("discards a late page after its filter request is aborted", async () => {
    let finish!: (page: HotKeyAPI.PageViewCollectionCoverageView_) => void;
    vi.mocked(listCollectionCoverage).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const controller = new AbortController();
    const pending = readCoveragePage(query, controller.signal, "cursor-1");
    controller.abort();
    finish({ items: [windowRow], next_cursor: null });
    expect(await pending).toBeNull();
    expect(listCollectionCoverage).toHaveBeenCalledWith(
      expect.objectContaining({
        source_key: "hotlist_weibo",
        cursor: "cursor-1",
      }),
      { signal: controller.signal },
    );
  });
});
