// @vitest-environment happy-dom

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
  topics: vi.fn(),
  reports: vi.fn(),
  replace: vi.fn(),
  query: "",
  deferLocationUpdates: false,
}));
const routeListeners = vi.hoisted(() => new Set<() => void>());
vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useSearchParams: () => {
      const query = useSyncExternalStore(
        (notify) => {
          routeListeners.add(notify);
          return () => {
            routeListeners.delete(notify);
          };
        },
        () => api.query,
      );
      return new URLSearchParams(query);
    },
  };
});
import { ApiRequestError } from "@/request";
vi.mock("@/api/jiankongzhuti", () => ({ listMonitorTopics: api.topics }));
vi.mock("@/api/ribao", () => ({ listReports: api.reports }));

import { ReportList } from "@/app/reports/components/report-list";
const originalReplaceState = window.history.replaceState.bind(window.history);
beforeEach(() => {
  api.deferLocationUpdates = false;
  originalReplaceState(null, "", "/reports");
  vi.spyOn(window.history, "replaceState").mockImplementation(
    (state, unused, href) => {
      originalReplaceState(state, unused, href);
      api.replace(href);
      if (!api.deferLocationUpdates) {
        api.query = window.location.search.slice(1);
        routeListeners.forEach((notify) => notify());
      }
    },
  );
});

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
  vi.restoreAllMocks();
  vi.resetAllMocks();
  api.query = "";
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

it("restores report filters from a shared URL and persists a period change", async () => {
  api.query =
    "kind=weekly&topic_id=topic-one&date_from=2026-10-01&date_to=2026-10-08";
  originalReplaceState(null, "", `/reports?${api.query}`);
  api.topics.mockResolvedValue({ items: [], next_cursor: null });
  api.reports.mockResolvedValue({ items: [], next_cursor: null });
  render(<ReportList />);
  await waitFor(() =>
    expect(api.reports).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "weekly",
        topic_id: "topic-one",
        date_from: "2026-10-01",
        date_to: "2026-10-08",
      }),
      expect.anything(),
    ),
  );
  fireEvent.click(screen.getByRole("radio", { name: "日报" }));
  const [href] = api.replace.mock.calls[0];
  const query = new URL(href, "https://hotkey.test").searchParams;
  expect(query.get("kind")).toBe("daily");
  expect(query.get("topic_id")).toBe("topic-one");
  expect(query.get("date_from")).toBe("2026-10-01");
  expect(window.location.search).toContain("kind=daily");
});

it.each([401, 403])(
  "clears old report titles when pagination loses permission (%s)",
  async (status) => {
    api.topics.mockResolvedValue({ items: [], next_cursor: null });
    api.reports
      .mockResolvedValueOnce({ items: [report], next_cursor: "next" })
      .mockRejectedValueOnce(
        new ApiRequestError({
          kind: "http",
          status,
          code: "permission_denied",
          message: "请求被拒绝",
        }),
      );
    render(<ReportList />);
    fireEvent.click(await screen.findByRole("button", { name: "加载更多" }));
    await screen.findByRole("heading", { name: "暂时无法访问报告" });
    expect(screen.queryByText("AI 产品", { exact: false })).toBeNull();
    expect(screen.queryByRole("link", { name: "查看报告" })).toBeNull();
    expect(screen.queryByRole("button", { name: "加载更多" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  },
);

it.each([401, 403])(
  "shows report permission denial on the initial read (%s)",
  async (status) => {
    api.topics.mockResolvedValue({ items: [], next_cursor: null });
    api.reports.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status,
        code: "permission_denied",
        message: "请求被拒绝",
      }),
    );
    render(<ReportList />);
    await screen.findByRole("heading", { name: "暂时无法访问报告" });
    expect(screen.queryByRole("alert")).toBeNull();
  },
);

it("merges consecutive filter changes while the router snapshot is delayed", async () => {
  api.topics.mockResolvedValue({ items: [], next_cursor: null });
  api.reports.mockResolvedValue({ items: [], next_cursor: null });
  render(<ReportList />);
  fireEvent.click(screen.getByRole("button", { name: "筛选报告" }));
  api.deferLocationUpdates = true;
  act(() => {
    fireEvent.change(screen.getByLabelText("开始日期"), {
      target: { value: "2026-10-01" },
    });
    fireEvent.change(screen.getByLabelText("结束日期"), {
      target: { value: "2026-10-08" },
    });
  });
  const query = new URLSearchParams(window.location.search);
  expect(query.get("date_from")).toBe("2026-10-01");
  expect(query.get("date_to")).toBe("2026-10-08");
  act(() => {
    api.query = query.toString();
    routeListeners.forEach((notify) => notify());
  });
  await waitFor(() =>
    expect(api.reports).toHaveBeenLastCalledWith(
      expect.objectContaining({
        date_from: "2026-10-01",
        date_to: "2026-10-08",
      }),
      expect.anything(),
    ),
  );
});
