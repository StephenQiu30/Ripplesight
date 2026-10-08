// @vitest-environment happy-dom
import { expectOnePageHeading } from "../../../page-heading";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ list: vi.fn() }));
const toasts = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock("@/api/caijirenwu", () => ({ listCollectionJobs: api.list }));
vi.mock("sonner", () => ({ toast: toasts }));
vi.mock("@/app/jobs/components/job-health-summary", () => ({
  JobHealthSummary: () => null,
}));
afterEach(() => {
  if (document.body.textContent) expectOnePageHeading();
  cleanup();
  vi.clearAllMocks();
});

import { ApiRequestError } from "@/request";
import {
  JobHistory,
  JobHistoryCard,
  JobHistoryContent,
} from "@/app/jobs/components/job-history";

const job: HotKeyAPI.JobHistoryItemView = {
  id: "job-1",
  kind: "monitor.collect",
  source_key: "x",
  source_capability: "search",
  status: "partially_succeeded",
  requests_sent: 2,
  items_saved: 3,
  created_at: "2026-09-23T08:00:00Z",
  started_at: "2026-09-23T08:00:01Z",
  completed_at: "2026-09-23T08:00:03Z",
  next_run_at: null,
};

describe("job history card", () => {
  it("shows a localized status, persisted progress, and a detail link", () => {
    const html = renderToStaticMarkup(createElement(JobHistoryCard, { job }));

    expect(html).toContain("部分完成");
    expect(html).toContain("请求 2 次 · 已保存 3 条");
    expect(html).toContain('href="/jobs/job-1"');
    expect(html).not.toContain("scope");
    expect(html).not.toContain("operation_id");
  });
});

describe("job history content", () => {
  it("explains an empty history without implying a zero-result collection", () => {
    const html = renderToStaticMarkup(
      createElement(JobHistoryContent, {
        items: [],
        nextCursor: null,
        isLoadingMore: false,
        onLoadMore: () => {},
      }),
    );

    expect(html).toContain("尚无任务记录");
    expect(html).toContain("提交采集任务后");
    expect(html).not.toContain("当前账号");
    expect(html).not.toContain("加载更多");
  });

  it("shows detail navigation and pagination when another page exists", () => {
    const html = renderToStaticMarkup(
      createElement(JobHistoryContent, {
        items: [job],
        nextCursor: "job-1",
        isLoadingMore: false,
        onLoadMore: () => {},
      }),
    );

    expect(html).toContain('href="/jobs/job-1"');
    expect(html).toContain("加载更多");
  });
});

describe("job history pagination feedback", () => {
  it("toasts pagination failure while preserving records and the retry cursor", async () => {
    api.list
      .mockResolvedValueOnce({ items: [job], next_cursor: "next-page" })
      .mockRejectedValueOnce(new Error("network failure"))
      .mockResolvedValueOnce({
        items: [{ ...job, id: "job-two" }],
        next_cursor: null,
      });
    render(createElement(JobHistory));
    await screen.findByRole("link", { name: "查看详情" });
    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith("后续任务加载失败，请重试。"),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("link", { name: "查看详情" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));
    await waitFor(() =>
      expect(screen.getAllByRole("link", { name: "查看详情" })).toHaveLength(2),
    );
    expect(api.list.mock.calls[1][0].cursor).toBe("next-page");
    expect(api.list.mock.calls[2][0].cursor).toBe("next-page");
  });
});

it.each([401, 403])(
  "removes previous job details when pagination loses permission (%s)",
  async (status) => {
    api.list
      .mockResolvedValueOnce({ items: [job], next_cursor: "next" })
      .mockRejectedValueOnce(
        new ApiRequestError({
          kind: "http",
          status,
          code: "permission_denied",
          message: "请求被拒绝",
        }),
      );
    render(<JobHistory />);
    fireEvent.click(await screen.findByRole("button", { name: "加载更多" }));
    await screen.findByRole("heading", { name: "暂时无法访问任务记录" });
    expect(screen.queryByRole("link", { name: "查看详情" })).toBeNull();
    expect(screen.queryByText("请求 2 次 · 已保存 3 条")).toBeNull();
    expect(screen.queryByRole("button", { name: "加载更多" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  },
);

it.each([401, 403])(
  "shows job permission denial on the initial read (%s)",
  async (status) => {
    api.list.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status,
        code: "permission_denied",
        message: "请求被拒绝",
      }),
    );
    render(<JobHistory />);
    await screen.findByRole("heading", { name: "暂时无法访问任务记录" });
    expect(screen.queryByRole("alert")).toBeNull();
  },
);
