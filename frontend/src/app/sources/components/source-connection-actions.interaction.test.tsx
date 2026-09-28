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
vi.mock("@/api/laiyuannengli", () => ({ updateSourceConnection }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));

import { SourceConnectionActions } from "./source-connection-actions";

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
});
