// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EditorialSourceManager } from "@/app/editorial-sources/components/editorial-source-manager";

const api = vi.hoisted(() => ({
  listEditorialSourceProfiles: vi.fn(),
  getEditorialSourceIcon: vi.fn(),
  refreshEditorialSourceIcon: vi.fn(),
  listEditorialSourceGroupBacklogs: vi.fn(),
  reviewEditorialSourceGroupBacklog: vi.fn(),
  createEditorialSourceProfile: vi.fn(),
  updateEditorialSourceProfile: vi.fn(),
  listEditorialSourceRuns: vi.fn(),
  reviewEditorialSourceRun: vi.fn(),
  pollEditorialSource: vi.fn(),
  ingestExternalEditorialSource: vi.fn(),
  getExternalEditorialIngressReceipt: vi.fn(),
}));
vi.mock("@/api/bianjilaiyuan", () => api);

beforeEach(() => {
  vi.clearAllMocks();
  api.listEditorialSourceProfiles.mockResolvedValue([]);
  api.getEditorialSourceIcon.mockResolvedValue({
    status: "not_configured",
    variants: [],
  });
  api.listEditorialSourceGroupBacklogs.mockResolvedValue([]);
});
afterEach(cleanup);

describe("editable source operations", () => {
  it("requires an in-memory operator token and exposes all six types with truthful empty state", async () => {
    render(<EditorialSourceManager />);
    fireEvent.change(screen.getByLabelText("操作员令牌"), {
      target: { value: "controlled" },
    });
    fireEvent.click(screen.getByRole("button", { name: "读取来源" }));
    await screen.findByText(
      "暂无编辑来源。先创建关闭配置，再批准来源许可与保留策略。",
    );
    expect(api.listEditorialSourceProfiles).toHaveBeenCalledWith(
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-HotKey-Operator-Token": "controlled",
        }),
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "新增来源" }));
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(
      expect.arrayContaining([
        "RSS / Atom",
        "网页列表",
        "JSON 列表",
        "X 官方搜索",
        "公众号",
        "外部摄入",
      ]),
    );
    fireEvent.click(screen.getByRole("button", { name: "清除令牌" }));
    expect(
      (screen.getByLabelText("操作员令牌") as HTMLInputElement).value,
    ).toBe("");
  });
  it("creates only a disabled source and binds operation id, reason, policy version", async () => {
    api.createEditorialSourceProfile.mockResolvedValue({ id: "created" });
    render(<EditorialSourceManager />);
    fireEvent.change(screen.getByLabelText("操作员令牌"), {
      target: { value: "controlled" },
    });
    fireEvent.click(screen.getByRole("button", { name: "新增来源" }));
    fireEvent.change(screen.getByLabelText("来源名称"), {
      target: { value: "Official feed" },
    });
    fireEvent.change(screen.getByLabelText("配置 JSON"), {
      target: {
        value: JSON.stringify({
          kind: "rss",
          feed_url: "https://example.com/feed",
          allowed_hosts: ["example.com"],
        }),
      },
    });
    fireEvent.change(screen.getByLabelText("操作原因"), {
      target: { value: "Add controlled source" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建关闭来源" }));
    await waitFor(() =>
      expect(api.createEditorialSourceProfile).toHaveBeenCalled(),
    );
    expect(api.createEditorialSourceProfile.mock.calls[0][0]).toMatchObject({
      expected_revision: 0,
      enabled: false,
      reason: "Add controlled source",
      policy_version: 1,
    });
    expect(
      api.createEditorialSourceProfile.mock.calls[0][0].operation_id,
    ).toBeTruthy();
  });
});

it("keeps the form's captured revision after a background profile refresh", async () => {
  const profile = {
    id: "profile-one",
    source_key: "ed_rss_profile",
    name: "Controlled feed",
    enabled: false,
    revision: 2,
    configuration_version: 2,
    configuration: {
      kind: "rss",
      feed_url: "https://example.com/feed",
      allowed_hosts: ["example.com"],
    },
    participation_mode: "editorial",
    tier: "T3",
    first_party: false,
    connection_id: null,
    connection_version: null,
    policy_version: 1,
    interval_minutes: 30,
    health: "unknown",
    failure_count: 0,
    last_fetch_at: null,
    last_ok_at: null,
    next_fetch_at: null,
    has_backlog: false,
  };
  api.listEditorialSourceProfiles
    .mockResolvedValueOnce([profile])
    .mockResolvedValue([{ ...profile, revision: 3, configuration_version: 3 }]);
  api.updateEditorialSourceProfile.mockResolvedValue(profile);
  render(<EditorialSourceManager />);
  fireEvent.change(screen.getByLabelText("操作员令牌"), {
    target: { value: "controlled" },
  });
  fireEvent.click(screen.getByRole("button", { name: "读取来源" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "管理 Controlled feed" }),
  );
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "读取来源" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole("button", { name: "读取来源" }));
  await screen.findByText(/修订 3 · 配置版本 3/);
  expect(screen.getByText(/本表单预期修订 2/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("操作原因"), {
    target: { value: "Controlled stale form" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存来源修订" }));
  await waitFor(() =>
    expect(api.updateEditorialSourceProfile).toHaveBeenCalled(),
  );
  expect(
    api.updateEditorialSourceProfile.mock.calls[0][1].expected_revision,
  ).toBe(2);
});

it("mounts the dedicated ingress receipt for a real external profile rather than treating its batch as a JobView", async () => {
  const profile = {
    id: "external-profile",
    source_key: "ed_external_profile",
    name: "Controlled external",
    enabled: true,
    revision: 3,
    configuration_version: 2,
    configuration: { kind: "external" },
    participation_mode: "editorial",
    tier: "T3",
    first_party: false,
    connection_id: null,
    connection_version: null,
    policy_version: 1,
    interval_minutes: 30,
    health: "unknown",
    failure_count: 0,
    last_fetch_at: null,
    last_ok_at: null,
    next_fetch_at: null,
    has_backlog: false,
  };
  api.listEditorialSourceProfiles.mockResolvedValue([profile]);
  api.ingestExternalEditorialSource.mockResolvedValue({
    job: { id: "ingress-job", status: "queued" },
    profile_id: profile.id,
    run_id: "ingress-run",
    configuration_version: 2,
    received: 1,
    items: [{ index: 0, status: "pending" }],
  });
  render(<EditorialSourceManager />);
  fireEvent.change(screen.getByLabelText("操作员令牌"), {
    target: { value: "controlled-operator-token" },
  });
  fireEvent.click(screen.getByRole("button", { name: "读取来源" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "管理 Controlled external" }),
  );
  fireEvent.change(screen.getByLabelText("来源专属令牌"), {
    target: { value: "controlled-source-token-12345678" },
  });
  fireEvent.change(screen.getByLabelText("材料 JSON 数组"), {
    target: { value: '[{"identity_key":"one"}]' },
  });
  fireEvent.click(screen.getByRole("button", { name: "受理材料摄入" }));
  await screen.findByText(/等待处理/);
  expect(
    screen.getByRole("link", { name: "查看任务 ingress-job" }),
  ).toBeTruthy();
  expect(api.ingestExternalEditorialSource.mock.calls[0][2].headers).toEqual({
    "X-HotKey-Source-Token": "controlled-source-token-12345678",
    "X-HotKey-CSRF": "1",
  });
  expect(api.getExternalEditorialIngressReceipt).not.toHaveBeenCalled();
});
