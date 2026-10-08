// @vitest-environment happy-dom

import { createElement } from "react";
import { ApiRequestError } from "@/request";
import { renderToStaticMarkup } from "react-dom/server";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));
afterEach(() => vi.clearAllMocks());

const api = vi.hoisted(() => ({
  list: vi.fn(),
  sources: vi.fn(),
  topics: vi.fn(),
}));
vi.mock("@/api/zuopinziliao", () => ({ listContentRecords: api.list }));
vi.mock("@/api/laiyuannengli", () => ({ listSourceCapabilities: api.sources }));
vi.mock("@/api/jiankongzhuti", () => ({ listMonitorTopics: api.topics }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import {
  ContentAnalysisStatus,
  ContentList,
  TimelineBasis,
  contentListParams,
} from "@/app/content/components/content-list";

const filters = {
  sourceKey: "hn_algolia",
  topicId: "d0e34b3d-e2b5-4c32-8436-741ca2015cc1",
  startDate: "2026-09-27",
  endDate: "2026-09-28",
  analysisState: "pending" as const,
};

const content: HotKeyAPI.ContentRecordSummaryView = {
  id: "af79ab61-5fe5-46af-91dd-b4103242a2ec",
  source_key: "hn_algolia",
  object_type: "post",
  native_scope: null,
  external_id: "controlled-1",
  identity_basis: null,
  latest_observation: {
    id: "0cc7354b-2e0c-4634-aaf1-26b8805cccaa",
    observed_at: "2026-09-28T08:00:00Z",
    received_at: "2026-09-28T08:00:00Z",
    published_at: null,
    published_at_fractional_digits: null,
    canonical_url: null,
    final_url: null,
    author_external_id: null,
    metrics: {
      like_count: null,
      comment_count: null,
      repost_count: null,
      view_count: null,
      play_count: null,
      danmaku_count: null,
    },
    content_version: null,
  },
  current_visibility: null,
  discovery_count: 1,
  timeline_at: "2026-09-28T07:00:00Z",
  timeline_basis: "first_observed_at",
  analysis_state: "pending",
  analysis_relevant: null,
};

describe("content list filters", () => {
  it("retains text search when loading another page and omits an empty query", () => {
    expect(
      contentListParams({ ...filters, query: "  OpenAI 模型  " }, "next"),
    ).toMatchObject({
      q: "OpenAI 模型",
      cursor: "next",
    });
    expect(contentListParams({ ...filters, query: "   " })).not.toHaveProperty(
      "q",
    );
  });

  it("rejects excessive search input before issuing a request", () => {
    expect(() =>
      contentListParams({ ...filters, query: "a b c d e f g" }),
    ).toThrow("搜索");
    expect(() =>
      contentListParams({ ...filters, query: "a".repeat(201) }),
    ).toThrow("搜索");
    expect(() => contentListParams({ ...filters, query: "a\u0000b" })).toThrow(
      "搜索",
    );
  });

  it("converts inclusive Beijing dates into a half-open UTC window and retains the cursor", () => {
    expect(contentListParams(filters, "page-two")).toEqual({
      source_key: "hn_algolia",
      topic_id: filters.topicId,
      starts_at: "2026-09-26T16:00:00.000Z",
      ends_at: "2026-09-28T16:00:00.000Z",
      analysis_state: "pending",
      cursor: "page-two",
      limit: 20,
    });
  });

  it("rejects incomplete, reversed, excessive and topicless state filters", () => {
    expect(() => contentListParams({ ...filters, endDate: "" })).toThrow(
      "完整",
    );
    expect(() =>
      contentListParams({ ...filters, endDate: "2026-09-26" }),
    ).toThrow("最多 31 天");
    expect(() =>
      contentListParams({ ...filters, endDate: "2026-10-29" }),
    ).toThrow("最多 31 天");
    expect(() => contentListParams({ ...filters, topicId: "" })).toThrow(
      "先选择主题",
    );
  });

  it("shows discovery time and keeps pending distinct from a valid relevance result", () => {
    expect(
      renderToStaticMarkup(createElement(TimelineBasis, { content })),
    ).toContain("首次发现");
    expect(
      renderToStaticMarkup(createElement(ContentAnalysisStatus, { content })),
    ).toContain("等待标注");
    const valid = { ...content, analysis_state: "valid" as const };
    expect(
      renderToStaticMarkup(
        createElement(ContentAnalysisStatus, {
          content: { ...valid, analysis_relevant: false },
        }),
      ),
    ).toContain("不相关");
    expect(
      renderToStaticMarkup(
        createElement(ContentAnalysisStatus, {
          content: { ...content, analysis_state: "missing" },
        }),
      ),
    ).toContain("暂无标注记录");
  });
});

beforeEach(() => {
  api.sources.mockResolvedValue({ items: [], next_cursor: null });
  api.topics.mockResolvedValue({ items: [], next_cursor: null });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const laterContent = {
  ...content,
  id: "second-content",
  external_id: "second-record",
};

describe("content list request recovery", () => {
  it("keeps records after append failure and retries the same cursor", async () => {
    api.list.mockResolvedValueOnce({
      items: [content],
      next_cursor: "page-two",
    });
    api.list.mockRejectedValueOnce(new Error("network failure"));
    api.list.mockResolvedValueOnce({
      items: [laterContent],
      next_cursor: null,
    });
    render(createElement(ContentList));
    await screen.findByRole("link", { name: content.external_id });
    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith("后续作品加载失败，请重试。"),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      screen.getByRole("link", { name: content.external_id }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));
    await screen.findByRole("link", { name: laterContent.external_id });
    expect(
      screen.getByRole("link", { name: content.external_id }),
    ).toBeTruthy();
    expect(
      api.list.mock.calls.slice(1).map(([params]) => params.cursor),
    ).toEqual(["page-two", "page-two"]);
    expect(screen.queryByRole("button", { name: "加载更多" })).toBeNull();
  });

  it("cancels an in-flight append when filters change and ignores its late response", async () => {
    let resolveOld!: (
      value: HotKeyAPI.PageViewContentRecordSummaryView_,
    ) => void;
    api.list.mockResolvedValueOnce({
      items: [content],
      next_cursor: "page-two",
    });
    api.list.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    );
    api.list.mockResolvedValueOnce({
      items: [laterContent],
      next_cursor: null,
    });
    render(createElement(ContentList));
    await screen.findByRole("link", { name: content.external_id });
    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));
    const oldSignal = api.list.mock.calls[1][1].signal as AbortSignal;
    fireEvent.click(screen.getByRole("button", { name: "筛选" }));
    fireEvent.change(screen.getByLabelText("开始日期"), {
      target: { value: "2026-09-27" },
    });
    fireEvent.change(screen.getByLabelText("结束日期（含）"), {
      target: { value: "2026-09-28" },
    });
    fireEvent.click(screen.getByRole("button", { name: "应用筛选" }));
    await screen.findByRole("link", { name: laterContent.external_id });
    expect(oldSignal.aborted).toBe(true);
    await act(async () => {
      resolveOld({
        items: [{ ...content, id: "stale", external_id: "stale-record" }],
        next_cursor: null,
      });
    });
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: "stale-record" })).toBeNull(),
    );
    expect(
      screen.getByRole("link", { name: laterContent.external_id }),
    ).toBeTruthy();
  });
});

it.each([401, 403])(
  "clears old content and pagination after permission denial (%s)",
  async (status) => {
    api.list
      .mockResolvedValueOnce({ items: [content], next_cursor: "next" })
      .mockRejectedValueOnce(
        new ApiRequestError({
          kind: "http",
          status,
          code: "permission_denied",
          message: "请求被拒绝",
        }),
      );
    render(<ContentList />);
    fireEvent.click(await screen.findByRole("button", { name: "加载更多" }));
    await screen.findByRole("heading", { name: "暂时无法访问作品资料" });
    expect(screen.queryByRole("button", { name: "加载更多" })).toBeNull();
    expect(
      screen.queryByRole("link", { name: content.external_id }),
    ).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  },
);

it.each([401, 403])(
  "shows content permission denial on the initial read (%s)",
  async (status) => {
    api.list.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status,
        code: "permission_denied",
        message: "请求被拒绝",
      }),
    );
    render(<ContentList />);
    await screen.findByRole("heading", { name: "暂时无法访问作品资料" });
    expect(screen.queryByRole("alert")).toBeNull();
  },
);
