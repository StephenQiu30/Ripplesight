// @vitest-environment happy-dom

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { CoverageIdentityCounts } from "@/app/sources/components/coverage-identity-counts";

afterEach(cleanup);

vi.mock("@/api/caijifugai", () => ({
  getCollectionCoverage: vi.fn(),
  getCollectionCoverageMetrics: vi.fn(),
  listCollectionCoverage: vi.fn(),
}));

import { listCollectionCoverage } from "@/api/caijifugai";

import { CoverageWindowDetail } from "@/app/sources/components/coverage-window-detail";
import { CoverageWindowTable } from "@/app/sources/components/coverage-window-table";
import {
  coverageQueryFromDraft,
  coverageUrl,
  parseCoverageQuery,
  readCoveragePage,
  shanghaiLocalToUtc,
  utcToShanghaiLocal,
  windowMatchesQuery,
} from "@/app/sources/components/source-coverage-panel";

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
  stored_observation_count: null,
  unique_content_count: null,
  identity_count_basis: null,
  updated_count: null,
  unchanged_count: null,
  unclassified_count: null,
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

    const detail = renderToStaticMarkup(
      createElement(CoverageWindowDetail, { row: windowRow, onClose: vi.fn() }),
    );
    expect(detail).toContain("这个到期窗口没有关联 Job");
    expect(detail).toContain("当前连接版本");
    expect(detail).toContain("v3");
    expect(detail).toContain("Job 固定连接版本");
    expect(detail).toContain("budget_exhausted");
    expect(detail).toContain("未知");
    expect(detail).toContain(">0</dd>");
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

describe("coverage identity accounting display", () => {
  const mixed: HotKeyAPI.CollectionCoverageView = {
    ...windowRow,
    identity_count_basis: "retained_receipt_identity_v1",
    observed_count: 20,
    stored_observation_count: 12,
    unique_content_count: 8,
    inserted_count: 2,
    updated_count: 3,
    unchanged_count: 2,
    unclassified_count: 1,
    deduplicated_count: 10,
  };

  function fact(label: string) {
    const group = screen.getByText(label, { selector: "dt" }).parentElement;
    if (group === null) throw new Error("definition group missing");
    return within(group);
  }

  it("keeps raw returns, stored observations and unique identities as separate denominators", () => {
    render(createElement(CoverageIdentityCounts, { row: mixed }));
    expect(fact("上游返回").getByText("20 条")).toBeDefined();
    expect(fact("持久观察").getByText("12 条")).toBeDefined();
    expect(fact("唯一身份").getByText("8 个唯一身份")).toBeDefined();
    for (const [label, count] of [
      ["新增", 2],
      ["更新", 3],
      ["未变", 2],
      ["无法比较", 1],
    ]) {
      expect(fact(String(label)).getByText(`${count} 个身份`)).toBeDefined();
      expect(fact(String(label)).getByText("分母：8 个唯一身份")).toBeDefined();
    }
    expect(fact("旧口径重复观察").getByText("10 条")).toBeDefined();
    expect(
      fact("旧口径重复观察").getByText(/不能作为未变数或与四类相加/),
    ).toBeDefined();
    expect(screen.getByText(/删除历史后可能改变/)).toBeDefined();
  });

  it("shows explicit zero identities with a zero denominator without inventing a percentage", () => {
    const row = {
      ...mixed,
      observed_count: 0,
      stored_observation_count: 0,
      unique_content_count: 0,
      inserted_count: 0,
      updated_count: 0,
      unchanged_count: 0,
      unclassified_count: 0,
      deduplicated_count: 0,
    };
    const { container } = render(
      createElement(CoverageIdentityCounts, { row }),
    );
    expect(screen.getAllByText("0 个身份")).toHaveLength(4);
    expect(screen.getAllByText("分母：0 个唯一身份")).toHaveLength(4);
    expect(container.textContent).not.toMatch(/NaN|Infinity|%/);
  });

  it("preserves unknown numerators and denominator independently from known zeros", () => {
    render(
      createElement(CoverageIdentityCounts, {
        row: {
          ...mixed,
          unique_content_count: null,
          updated_count: null,
          unchanged_count: 0,
          unclassified_count: null,
        },
      }),
    );
    expect(fact("新增").getByText("2 个身份")).toBeDefined();
    expect(fact("更新").getByText("未知")).toBeDefined();
    expect(fact("未变").getByText("0 个身份")).toBeDefined();
    expect(screen.getAllByText("分母：未知")).toHaveLength(4);
  });

  it.each([null, "retained_receipt_identity_v2"])(
    "does not infer categories for unsupported basis %s",
    (basis) => {
      render(
        createElement(CoverageIdentityCounts, {
          row: { ...mixed, identity_count_basis: basis },
        }),
      );
      expect(screen.getByText(/未提供可核对的身份计量口径/)).toBeDefined();
      for (const label of ["新增", "更新", "未变", "无法比较"]) {
        expect(fact(label).getByText("未知")).toBeDefined();
        expect(fact(label).getByText("分母：未知")).toBeDefined();
      }
      expect(fact("旧口径重复观察").getByText("10 条")).toBeDefined();
      expect(screen.queryByText("10 个身份")).toBeNull();
    },
  );

  it("handles older responses missing the new fields without showing undefined or using legacy inserted counts", () => {
    const row = { ...windowRow, inserted_count: 14, deduplicated_count: 7 };
    for (const field of [
      "identity_count_basis",
      "stored_observation_count",
      "unique_content_count",
      "updated_count",
      "unchanged_count",
      "unclassified_count",
    ])
      Reflect.deleteProperty(row, field);
    const { container } = render(
      createElement(CoverageIdentityCounts, { row }),
    );
    expect(fact("持久观察").getByText("未知")).toBeDefined();
    expect(fact("新增").getByText("未知")).toBeDefined();
    expect(fact("旧口径重复观察").getByText("7 条")).toBeDefined();
    expect(container.textContent).not.toContain("undefined");
    expect(screen.queryByText("14 个身份")).toBeNull();
  });
});

describe("scheduled skipped query receipts", () => {
  it.each(["source_unavailable", "quiet", "budget", "rate_limited"] as const)(
    "shows frozen queries and version for %s without claiming collection",
    (reason) => {
      render(
        createElement(CoverageWindowDetail, {
          row: {
            ...windowRow,
            capability: "search",
            query_plan: {
              version: 1,
              topic_version: 2,
              max_queries: null,
              collection: null,
              queries: ["Brand", "Other"].map((query, query_index) => ({
                query_index,
                query,
                admitted: false,
                skip_reason: reason,
              })),
            },
          },
          onClose: vi.fn(),
        }),
      );
      const receipt = within(
        screen.getByRole("region", { name: "查询受理回执" }),
      );
      expect(receipt.getByText("冻结主题版本：v2")).toBeTruthy();
      expect(receipt.getByText("Brand")).toBeTruthy();
      expect(receipt.getByText("Other")).toBeTruthy();
      expect(receipt.getAllByText(/未受理（/)).toHaveLength(2);
      expect(receipt.getByText(/未受理查询不计为零结果/)).toBeTruthy();
      expect(receipt.queryByText(/已受理/)).toBeNull();
      expect(screen.queryByRole("link", { name: /查看任务/ })).toBeNull();
    },
  );
  it("preserves unknown historical receipts and excludes non-search capabilities", () => {
    const view = render(
      createElement(CoverageWindowDetail, {
        row: { ...windowRow, capability: "search" },
        onClose: vi.fn(),
      }),
    );
    expect(screen.getByText("此次运行未保存逐查询受理记录。")).toBeTruthy();
    view.rerender(
      createElement(CoverageWindowDetail, { row: windowRow, onClose: vi.fn() }),
    );
    expect(screen.queryByRole("region", { name: "查询受理回执" })).toBeNull();
  });
});
