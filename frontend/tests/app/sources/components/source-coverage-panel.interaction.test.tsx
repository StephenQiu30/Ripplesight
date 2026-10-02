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
  return {
    get href() {
      return href;
    },
    reset(value: string) {
      href = value;
      listeners.forEach((listener) => listener());
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    router: {
      replace(value: string) {
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

import { SourceCoveragePanel } from "@/app/sources/components/source-coverage-panel";

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
    vi.mocked(listSourceCapabilities).mockResolvedValue({
      items: [
        {
          source_key: "new_source",
          display_name: "新来源",
          rollout_role: "candidate",
          status: "available",
          connection_version: 1,
          connection_id: "connection-1",
          connection_status: "active",
          has_credentials: false,
          credential_configured: false,
          credential_update_available: false,
          allowed_hosts: ["example.com"],
          capabilities: [],
        },
      ],
      next_cursor: null,
    });
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

    fireEvent.keyDown(screen.getByRole("combobox", { name: "来源" }), {
      key: "Enter",
    });
    fireEvent.click(await screen.findByRole("option", { name: "新来源" }));
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

  it("retries a business failure and keeps 403 scoped inside the page", async () => {
    vi.mocked(listCollectionCoverage).mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 503,
        code: "demo_scope_conflict",
        message: "历史数据分区冲突",
        requestId: "request-demo-scope",
      }),
    );
    const { unmount } = render(<SourceCoveragePanel />);
    expect(await screen.findByText(/历史数据分区冲突/)).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain(
      "request-demo-scope",
    );
    expect(navigation.href).toBe(url("old_source"));
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    expect(await screen.findByText("此筛选下暂无到期窗口")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
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

  it("shows a source option error without blocking coverage and retries it", async () => {
    vi.mocked(listSourceCapabilities).mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 502,
        code: "upstream_error",
        message: "来源服务暂不可用",
        requestId: "request-source-options",
      }),
    );
    render(<SourceCoveragePanel />);
    expect(await screen.findByText("来源选项加载失败")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain(
      "request-source-options",
    );
    expect(await screen.findByText("此筛选下暂无到期窗口")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(listSourceCapabilities).toHaveBeenCalledTimes(2);
    expect(navigation.href).toBe(url("old_source"));
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
