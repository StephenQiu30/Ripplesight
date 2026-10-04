// @vitest-environment happy-dom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));
afterEach(() => vi.clearAllMocks());

const api = vi.hoisted(() => ({ topics: vi.fn(), reports: vi.fn() }));
vi.mock("@/api/jiankongzhuti", () => ({ listMonitorTopics: api.topics }));
vi.mock("@/api/ribao", () => ({ listReports: api.reports }));

import { ReportList } from "@/app/reports/components/report-list";

const report: HotKeyAPI.ReportSummaryView = {
  id: "report-one",
  topic_id: "topic-one",
  topic_name: "AI 产品",
  kind: "daily",
  window_start: "2026-10-01T00:00:00Z",
  window_end: "2026-10-02T00:00:00Z",
  version: 1,
  generator: "template",
};

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("report reads from Swagger operations", () => {
  it("reads reports even when auxiliary topic options fail", async () => {
    api.topics.mockRejectedValue(new Error("topics unavailable"));
    api.reports.mockResolvedValue({ items: [report], next_cursor: null });
    render(<ReportList />);
    expect(await screen.findByRole("link", { name: "查看报告" })).toBeTruthy();
    expect(api.reports.mock.calls[0][0]).toMatchObject({
      kind: "daily",
      limit: 20,
    });
  });

  it("preserves the first page when pagination fails and retries the same cursor", async () => {
    api.topics.mockResolvedValue({ items: [], next_cursor: null });
    api.reports
      .mockResolvedValueOnce({ items: [report], next_cursor: "next-page" })
      .mockRejectedValueOnce(new Error("temporary failure"))
      .mockResolvedValueOnce({
        items: [{ ...report, id: "report-two", topic_name: "第二份报告" }],
        next_cursor: null,
      });
    render(<ReportList />);
    fireEvent.click(await screen.findByRole("button", { name: "加载更多" }));
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith("报告加载失败，请稍后重试。"),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));
    await waitFor(() =>
      expect(screen.getAllByRole("link", { name: "查看报告" })).toHaveLength(2),
    );
    expect(api.reports.mock.calls[1][0].cursor).toBe("next-page");
    expect(api.reports.mock.calls[2][0].cursor).toBe("next-page");
  });

  it("aborts the previous page when date filters change", async () => {
    api.topics.mockResolvedValue({ items: [], next_cursor: null });
    api.reports.mockResolvedValue({ items: [report], next_cursor: null });
    render(<ReportList />);
    await screen.findByRole("link", { name: "查看报告" });
    const firstSignal = api.reports.mock.calls[0][1].signal as AbortSignal;
    fireEvent.click(screen.getByRole("button", { name: "筛选报告" }));
    fireEvent.change(screen.getByLabelText("开始日期"), {
      target: { value: "2026-10-01" },
    });
    await waitFor(() => expect(api.reports).toHaveBeenCalledTimes(2));
    expect(firstSignal.aborted).toBe(true);
    expect(api.reports.mock.calls[1][0].date_from).toBe("2026-10-01");
  });
});

it("switches to weekly reports with a fresh cursor and aborts daily pagination", async () => {
  api.topics.mockResolvedValue({ items: [], next_cursor: null });
  api.reports
    .mockResolvedValueOnce({ items: [report], next_cursor: "daily-next" })
    .mockResolvedValueOnce({
      items: [{ ...report, id: "weekly-one", kind: "weekly" }],
      next_cursor: null,
    });
  render(<ReportList />);
  await screen.findByRole("button", { name: "加载更多" });
  const signal = api.reports.mock.calls[0][1].signal as AbortSignal;
  fireEvent.click(screen.getByRole("radio", { name: "周报" }));
  await waitFor(() => expect(api.reports).toHaveBeenCalledTimes(2));
  expect(signal.aborted).toBe(true);
  expect(api.reports.mock.calls[1][0]).toMatchObject({
    kind: "weekly",
    limit: 20,
  });
  expect(api.reports.mock.calls[1][0].cursor).toBeUndefined();
  expect(screen.queryByRole("button", { name: "加载更多" })).toBeNull();
});
