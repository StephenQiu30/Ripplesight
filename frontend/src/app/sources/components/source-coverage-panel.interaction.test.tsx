// @vitest-environment happy-dom

import { act } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const navigation = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  let href = "/sources";
  let externalNavigation: string | null = null;
  return {
    get href() {
      return href;
    },
    get externalNavigation() {
      return externalNavigation;
    },
    reset(value: string) {
      href = value;
      externalNavigation = null;
      listeners.forEach((listener) => listener());
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    router: {
      replace(value: string) {
        if (value === "/login") {
          externalNavigation = value;
          return;
        }
        href = value;
        listeners.forEach((listener) => listener());
      },
    },
    snapshot() {
      return href;
    },
  };
});

vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useRouter: () => navigation.router,
    useSearchParams: () =>
      new URL(
        useSyncExternalStore(
          navigation.subscribe,
          navigation.snapshot,
          navigation.snapshot,
        ),
        "http://localhost",
      ).searchParams,
  };
});

vi.mock("@/api/caijifugai", () => ({
  getCollectionCoverage: vi.fn(),
  getCollectionCoverageMetrics: vi.fn(),
  listCollectionCoverage: vi.fn(),
}));
vi.mock("@/api/laiyuannengli", () => ({ listSourceCapabilities: vi.fn() }));

import {
  getCollectionCoverageMetrics,
  listCollectionCoverage,
} from "@/api/caijifugai";
import { listSourceCapabilities } from "@/api/laiyuannengli";
import { ApiRequestError } from "@/request";

import { SourceCoveragePanel } from "./source-coverage-panel";

const START = "2026-09-27T00:00:00.000Z";
const END = "2026-09-28T00:00:00.000Z";

function url(sourceKey: string): string {
  const params = new URLSearchParams({
    start: START,
    end: END,
    source_key: sourceKey,
  });
  return `/sources?${params.toString()}`;
}

function row(sourceKey: string): HotKeyAPI.CollectionCoverageView {
  return {
    window_id: `window-${sourceKey}`,
    source_key: sourceKey,
    capability: "search",
    topic_id: null,
    due_at: "2026-09-27T11:00:00Z",
    window_start: "2026-09-27T10:30:00Z",
    window_end: "2026-09-27T11:00:00Z",
    admission_state: "accepted",
    admission_reason: null,
    current_connection_version: 1,
    job_connection_version: 1,
    job_id: `job-${sourceKey}`,
    job_status: "partially_succeeded",
    attempts: [],
    started_at: "2026-09-27T11:01:00Z",
    finished_at: "2026-09-27T11:02:00Z",
    last_success_at: null,
    coverage_status: "partial",
    terminal_evidence: null,
    stop_reason: "budget_exhausted",
    request_count: 1,
    request_attempt_count: 1,
    page_count: 1,
    observed_count: 1,
    inserted_count: 1,
    deduplicated_count: 0,
    analysis: null,
    budgets: [],
    gaps: [
      {
        starts_at: "2026-09-27T10:45:00Z",
        ends_at: "2026-09-27T11:00:00Z",
        reason: "budget_exhausted",
      },
    ],
    content_ids: [],
    snapshot_ids: [],
  };
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  navigation.reset(url("old_source"));
  vi.mocked(listSourceCapabilities).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
  vi.mocked(getCollectionCoverageMetrics).mockResolvedValue({
    metric_version: "test",
    start: START,
    end: END,
    cutoff_at: END,
    sources: [],
    analysis_status: "not_computable",
  });
  vi.mocked(listCollectionCoverage).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("source coverage interaction", () => {
  it("keeps the new filter visible when an old source response finishes late", async () => {
    let finishOld!: (page: HotKeyAPI.PageViewCollectionCoverageView_) => void;
    vi.mocked(listCollectionCoverage).mockImplementation(({ source_key }) =>
      source_key === "old_source"
        ? new Promise((resolve) => {
            finishOld = resolve;
          })
        : Promise.resolve({ items: [row("new_source")], next_cursor: null }),
    );

    render(<SourceCoveragePanel />);
    await waitFor(() => expect(finishOld).toBeTypeOf("function"));

    fireEvent.change(screen.getByLabelText("来源"), {
      target: { value: "new_source" },
    });
    fireEvent.click(screen.getByRole("button", { name: "查询窗口" }));

    await waitFor(() => expect(navigation.href).toContain("new_source"));
    await waitFor(() =>
      expect(screen.getAllByText("new_source").length).toBeGreaterThan(0),
    );
    const oldSignal = vi.mocked(listCollectionCoverage).mock.calls[0][1]
      ?.signal;
    expect(oldSignal?.aborted).toBe(true);

    await act(async () => {
      finishOld({ items: [row("old_source")], next_cursor: null });
    });
    expect(screen.queryByText("old_source")).toBeNull();
    expect(screen.getAllByText("new_source").length).toBeGreaterThan(0);
    expect(screen.getAllByText("部分结果").length).toBeGreaterThan(0);
  });

  it("redirects an expired session and keeps 403 scoped inside the page", async () => {
    vi.mocked(listCollectionCoverage).mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 401,
        code: "invalid_session",
        message: "会话失效",
      }),
    );
    const { unmount } = render(<SourceCoveragePanel />);
    await waitFor(() => expect(navigation.externalNavigation).toBe("/login"));
    unmount();

    navigation.reset(url("forbidden_source"));
    vi.mocked(listCollectionCoverage).mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 403,
        message: "无权查看",
      }),
    );
    render(<SourceCoveragePanel />);
    expect(await screen.findByText("记录不存在或无权查看")).toBeTruthy();
    expect(navigation.href).toContain("forbidden_source");
  });

  it.each([
    [
      "500",
      new ApiRequestError({
        kind: "http",
        status: 500,
        message: "服务暂时不可用",
      }),
    ],
    [
      "断网",
      new ApiRequestError({
        kind: "network",
        message: "无法连接服务",
      }),
    ],
  ])(
    "recovers from %s without dropping the URL filter",
    async (_case, error) => {
      navigation.reset(url("retry_source"));
      vi.mocked(listCollectionCoverage)
        .mockRejectedValueOnce(error)
        .mockResolvedValueOnce({ items: [], next_cursor: null });

      render(<SourceCoveragePanel />);
      expect(await screen.findByText("覆盖窗口加载失败")).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
      expect(await screen.findByText("此筛选下暂无到期窗口")).toBeTruthy();
      expect(navigation.href).toContain("retry_source");
      expect(vi.mocked(listCollectionCoverage)).toHaveBeenCalledTimes(2);
    },
  );
});
