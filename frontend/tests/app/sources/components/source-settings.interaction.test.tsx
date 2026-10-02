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

vi.mock("@/api/laiyuannengli", () => ({
  listSourceCapabilities: vi.fn(),
  updateSourceConnection: vi.fn(),
}));

import { listSourceCapabilities } from "@/api/laiyuannengli";
import { ApiRequestError } from "@/request";

import { SourceSettings } from "@/app/sources/components/source-settings";

const entry: HotKeyAPI.SourceEntryPointView = {
  status: "pending_verification",
  last_checked_at: null,
  last_persisted_success_at: null,
  stop_reason: null,
  next_action: "等待一次真实采集验证。",
};
const source: HotKeyAPI.SourcePlatformView = {
  source_key: "hackernews",
  display_name: "Hacker News",
  rollout_role: "required",
  status: "pending_verification",
  connection_version: 1,
  connection_id: "connection-1",
  connection_status: "active",
  has_credentials: false,
  credential_configured: false,
  credential_update_available: false,
  allowed_hosts: ["hacker-news.firebaseio.com"],
  capabilities: [
    {
      capability: "search",
      display_name: "关键词检索",
      manual: entry,
      scheduled: entry,
    },
  ],
};

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.mocked(listSourceCapabilities).mockResolvedValue({
    items: [source],
    next_cursor: null,
  });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("source settings", () => {
  it("keeps technical capability records behind the source detail tab", async () => {
    render(<SourceSettings />);
    const manage = await screen.findByRole("button", {
      name: "管理Hacker News",
    });
    expect(screen.queryByText("最近持久成功")).toBeNull();
    fireEvent.click(manage);
    expect(screen.getByRole("dialog", { name: "Hacker News" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "停用连接" })).toBeTruthy();
    expect(screen.queryByText("最近持久成功")).toBeNull();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "能力详情" }), {
      button: 0,
      ctrlKey: false,
    });
    expect(await screen.findAllByText("最近持久成功")).toHaveLength(2);
    expect(screen.getAllByText("待验证").length).toBeGreaterThan(0);
    expect(screen.queryByText("可用")).toBeNull();
  });

  it("retries a read failure and displays its request ID without removing the source list", async () => {
    render(<SourceSettings />);
    await screen.findByRole("button", { name: "管理Hacker News" });
    vi.mocked(listSourceCapabilities).mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 503,
        message: "来源状态暂不可用",
        requestId: "source-request-1",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "刷新状态" }));
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      expect.stringContaining("source-request-1"),
    );
    expect(
      screen.getByRole("button", { name: "管理Hacker News" }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(listSourceCapabilities).toHaveBeenCalledTimes(3);
  });

  it("aborts the source read on unmount and discards its late result", async () => {
    let finish!: (page: HotKeyAPI.PageViewSourcePlatformView_) => void;
    vi.mocked(listSourceCapabilities).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const view = render(<SourceSettings />);
    const signal = vi.mocked(listSourceCapabilities).mock.calls[0][0]?.signal;
    view.unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      finish({ items: [source], next_cursor: null });
    });
    expect(screen.queryByText("Hacker News")).toBeNull();
  });
});
