// @vitest-environment happy-dom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const updateSourceConnection = vi.hoisted(() => vi.fn().mockResolvedValue({}));
const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));
afterEach(() => vi.clearAllMocks());

vi.mock("@/api/laiyuannengli", () => ({ updateSourceConnection }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

import { SourceConnectionActions } from "@/app/sources/components/source-connection-actions";
import { ApiRequestError } from "@/request";

afterEach(() => {
  cleanup();
  updateSourceConnection.mockClear();
});

const platform: HotKeyAPI.SourcePlatformView = {
  source_key: "bilibili",
  display_name: "B 站关键词与评论",
  rollout_role: "candidate",
  status: "restricted",
  connection_version: 3,
  connection_id: "00000000-0000-0000-0000-000000000001",
  connection_status: "disabled",
  safety_stop_reason: "rate_limited",
  safety_stopped_at: "2026-09-28T09:00:00Z",
  safety_trigger_job_id: "00000000-0000-0000-0000-000000000002",
  has_credentials: false,
  credential_configured: false,
  credential_update_available: false,
  allowed_hosts: ["www.bilibili.com"],
  capabilities: [],
};

describe("Bilibili safety recovery", () => {
  it("shows the stop reason and requires owner review before sending recovery", async () => {
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(
      <SourceConnectionActions platform={platform} onChanged={onChanged} />,
    );
    expect(screen.getByText(/B 站访问频繁，来源已暂停/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重新启用" }));
    const confirm = screen.getByRole("button", { name: "确认" });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox"));
    expect((confirm as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(confirm);
    await waitFor(() => expect(updateSourceConnection).toHaveBeenCalledOnce());
    expect(updateSourceConnection).toHaveBeenCalledWith(
      { source_key: "bilibili" },
      { expected_version: 3, status: "active", owner_confirmed: true },
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  });
  it("cancels a confirmation without changing the connection", async () => {
    render(<SourceConnectionActions platform={platform} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "重新启用" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(updateSourceConnection).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "重新启用" }),
    );
  });

  it("reenables a configured public source without a credential requirement", async () => {
    const onChanged = vi.fn().mockResolvedValue(undefined);
    render(
      <SourceConnectionActions
        platform={{
          ...platform,
          source_key: "hackernews",
          display_name: "Hacker News",
          safety_stop_reason: null,
        }}
        onChanged={onChanged}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "重新启用" }));
    expect(screen.queryByRole("checkbox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "确认" }));
    await waitFor(() =>
      expect(updateSourceConnection).toHaveBeenCalledWith(
        { source_key: "hackernews" },
        { expected_version: 3, status: "active", owner_confirmed: false },
      ),
    );
    expect(onChanged).toHaveBeenCalledOnce();
  });

  it("configures a public web connection with explicit hosts and the current version", async () => {
    render(
      <SourceConnectionActions
        platform={{
          ...platform,
          source_key: "web",
          display_name: "公开网页",
          status: "unconfigured",
          connection_version: null,
          connection_status: null,
          safety_stop_reason: null,
          allowed_hosts: [],
        }}
        onChanged={vi.fn().mockResolvedValue(undefined)}
      />,
    );
    const configure = screen.getByRole("button", { name: "配置连接" });
    expect((configure as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "允许访问的域名" }), {
      target: { value: "example.com\nnews.example.com" },
    });
    fireEvent.click(configure);
    fireEvent.click(screen.getByRole("button", { name: "确认" }));
    await waitFor(() =>
      expect(updateSourceConnection).toHaveBeenCalledWith(
        { source_key: "web" },
        {
          expected_version: 0,
          status: "active",
          owner_confirmed: false,
          allowed_hosts: ["example.com", "news.example.com"],
        },
      ),
    );
  });

  it("shows a version conflict without automatically repeating the write", async () => {
    const onChanged = vi.fn().mockResolvedValue(undefined);
    updateSourceConnection.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 409,
        message: "连接版本已变化，请刷新后重试。",
        requestId: "source-version-conflict",
      }),
    );
    render(
      <SourceConnectionActions
        platform={{
          ...platform,
          source_key: "hackernews",
          safety_stop_reason: null,
        }}
        onChanged={onChanged}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "重新启用" }));
    fireEvent.click(screen.getByRole("button", { name: "确认" }));
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith(
        "连接版本已变化，请刷新后重试。 请求编号：source-version-conflict",
        expect.objectContaining({
          action: expect.objectContaining({ label: "刷新状态" }),
        }),
      ),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(updateSourceConnection).toHaveBeenCalledOnce();
    expect(onChanged).not.toHaveBeenCalled();
    toasts.error.mock.calls.at(-1)?.[1].action.onClick();
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
    expect(updateSourceConnection).toHaveBeenCalledOnce();
  });
});
