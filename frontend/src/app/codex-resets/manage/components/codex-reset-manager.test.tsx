// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/request";
import { CodexResetManager } from "./codex-reset-manager";

const api = vi.hoisted(() => ({
  getCodexResetConfiguration: vi.fn(),
  configureCodexResetMonitor: vi.fn(),
  getCodexResetSnapshot: vi.fn(),
  listCodexResetScanGaps: vi.fn(),
  listCodexResetPosts: vi.fn(),
  correctCodexResetEvent: vi.fn(),
  reviewCodexResetPost: vi.fn(),
  reviewCodexResetScanGap: vi.fn(),
  pollCodexResetMonitor: vi.fn(),
  relinkCodexResetPost: vi.fn(),
}));
vi.mock("@/api/zhongzhigonggao", () => api);
beforeEach(() => {
  vi.clearAllMocks();
  api.getCodexResetConfiguration.mockResolvedValue(null);
});
afterEach(cleanup);

describe("announcement operational UI", () => {
  function linkedPosts() {
    api.getCodexResetConfiguration.mockResolvedValue({
      id: "monitor",
      enabled: false,
      revision: 7,
      configuration_version: 2,
      configuration: { author: "thsottiaux", source_key: "x" },
    });
    api.getCodexResetSnapshot.mockResolvedValue({
      events: [
        {
          id: "source-event",
          revision: 3,
          title: "原公告",
          kind: "direct_reset",
          status: "announced",
        },
        {
          id: "target-event",
          revision: 8,
          title: "目标公告",
          kind: "reset_credit",
          status: "announced",
        },
      ],
    });
    api.listCodexResetScanGaps.mockResolvedValue([]);
    api.listCodexResetPosts.mockResolvedValue([
      {
        id: "linked-post",
        text: "待改归属的官方帖子",
        external_id: "42",
        review_version: 19,
        failure_count: 0,
        event_ids: ["source-event"],
        url: "https://x.com/thsottiaux/status/42",
      },
    ]);
  }
  async function openRelink() {
    linkedPosts();
    render(<CodexResetManager />);
    await screen.findByText("监控修订 7 · 配置版本 2");
    fireEvent.change(screen.getByLabelText("操作员令牌"), {
      target: { value: "controlled" },
    });
    fireEvent.click(screen.getByRole("button", { name: "读取待复核与公告" }));
    await screen.findByText("待改归属的官方帖子");
    fireEvent.change(screen.getByLabelText("操作与复核原因"), {
      target: { value: "核对原帖后纠正关联" },
    });
    fireEvent.click(screen.getByRole("button", { name: "更改公告归属" }));
  }
  it("captures both event revisions instead of the post review version when moving a post", async () => {
    api.relinkCodexResetPost.mockResolvedValue({
      id: "linked-post",
      event_ids: ["target-event"],
    });
    await openRelink();
    fireEvent.change(screen.getByLabelText("目标公告"), {
      target: { value: "target-event" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存帖子归属" }));
    await waitFor(() =>
      expect(api.relinkCodexResetPost).toHaveBeenCalledTimes(1),
    );
    expect(api.relinkCodexResetPost.mock.calls[0]).toEqual([
      { monitor_id: "monitor", post_id: "linked-post" },
      {
        from_event_id: "source-event",
        to_event_id: "target-event",
        target_expected_revision: 8,
        review: {
          expected_revision: 3,
          reason: "核对原帖后纠正关联",
          actor: "operator",
          operation_id: expect.any(String),
        },
      },
      {
        headers: {
          "X-HotKey-Operator-Token": "controlled",
          "X-HotKey-CSRF": "1",
        },
      },
    ]);
  });
  it("explicitly clears a link with a null target and null target revision", async () => {
    api.relinkCodexResetPost.mockResolvedValue({
      id: "linked-post",
      event_ids: [],
    });
    await openRelink();
    fireEvent.click(screen.getByRole("button", { name: "保存帖子归属" }));
    await waitFor(() =>
      expect(api.relinkCodexResetPost).toHaveBeenCalledTimes(1),
    );
    expect(api.relinkCodexResetPost.mock.calls[0][1]).toMatchObject({
      from_event_id: "source-event",
      to_event_id: null,
      target_expected_revision: null,
      review: { expected_revision: 3 },
    });
  });
  it("reuses the same operation after an unconfirmed response and retains the captured revisions", async () => {
    api.relinkCodexResetPost.mockRejectedValueOnce(
      new ApiRequestError({ kind: "timeout", message: "受理响应丢失" }),
    );
    api.relinkCodexResetPost.mockResolvedValueOnce({
      id: "linked-post",
      event_ids: ["target-event"],
    });
    await openRelink();
    fireEvent.change(screen.getByLabelText("目标公告"), {
      target: { value: "target-event" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存帖子归属" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("alert").textContent).toContain("操作结果尚未确认");
    fireEvent.click(screen.getByRole("button", { name: "保存帖子归属" }));
    await waitFor(() =>
      expect(api.relinkCodexResetPost).toHaveBeenCalledTimes(2),
    );
    expect(api.relinkCodexResetPost.mock.calls[1][1]).toEqual(
      api.relinkCodexResetPost.mock.calls[0][1],
    );
  });
  it("discards a late relink response after clearing the operator context", async () => {
    let complete!: (value: object) => void;
    api.relinkCodexResetPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
    await openRelink();
    fireEvent.click(screen.getByRole("button", { name: "保存帖子归属" }));
    await waitFor(() =>
      expect(api.relinkCodexResetPost).toHaveBeenCalledTimes(1),
    );
    const reads = api.getCodexResetSnapshot.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "清除令牌" }));
    complete({ id: "linked-post", event_ids: [] });
    await waitFor(() =>
      expect(
        (screen.getByLabelText("操作员令牌") as HTMLInputElement).value,
      ).toBe(""),
    );
    expect(screen.queryByRole("region", { name: "帖子公告归属" })).toBeNull();
    expect(screen.queryByText("帖子归属与双方公告修订已保存。")).toBeNull();
    expect(api.getCodexResetSnapshot).toHaveBeenCalledTimes(reads);
  });
  it("creates a disabled configuration only with explicit reason and in-memory token", async () => {
    render(<CodexResetManager />);
    await screen.findByText("尚未配置公告监控");
    fireEvent.change(screen.getByLabelText("操作员令牌"), {
      target: { value: "controlled" },
    });
    fireEvent.change(screen.getByLabelText("操作与复核原因"), {
      target: { value: "Configure official source" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建关闭公告监控" }));
    await waitFor(() =>
      expect(api.configureCodexResetMonitor).toHaveBeenCalled(),
    );
    expect(api.configureCodexResetMonitor.mock.calls[0][0]).toMatchObject({
      expected_revision: 0,
      enabled: false,
      reason: "Configure official source",
      configuration: { author: "thsottiaux", source_key: "x" },
    });
    expect(
      api.configureCodexResetMonitor.mock.calls[0][1].headers[
        "X-HotKey-Operator-Token"
      ],
    ).toBe("controlled");
  });
  it("binds a manual unknown recognition retry to the displayed post review revision", async () => {
    api.getCodexResetConfiguration.mockResolvedValue({
      id: "monitor",
      enabled: false,
      revision: 7,
      configuration_version: 2,
      configuration: { author: "thsottiaux", source_key: "x" },
    });
    api.getCodexResetSnapshot.mockResolvedValue({ events: [] });
    api.listCodexResetScanGaps.mockResolvedValue([]);
    api.listCodexResetPosts.mockResolvedValue([
      {
        id: "post",
        text: "Controlled source announcement",
        external_id: "42",
        needs_review: true,
        reviewed: false,
        review_version: 4,
        failure_count: 1,
        failure_code: "model_request_unknown",
        published_at: "2026-10-02T02:00:00Z",
        url: "https://x.com/a/status/42",
      },
    ]);
    render(<CodexResetManager />);
    await screen.findByText("监控修订 7 · 配置版本 2");
    fireEvent.change(screen.getByLabelText("操作员令牌"), {
      target: { value: "controlled" },
    });
    fireEvent.click(screen.getByRole("button", { name: "读取待复核与公告" }));
    await screen.findByText("Controlled source announcement");
    fireEvent.change(screen.getByLabelText("操作与复核原因"), {
      target: { value: "Verified unknown result before retry" },
    });
    fireEvent.click(screen.getByRole("button", { name: "明确允许再次识别" }));
    await waitFor(() => expect(api.reviewCodexResetPost).toHaveBeenCalled());
    expect(api.reviewCodexResetPost.mock.calls[0][1]).toMatchObject({
      action: "retry",
      review: {
        expected_revision: 4,
        reason: "Verified unknown result before retry",
        actor: "operator",
      },
    });
  });
});
