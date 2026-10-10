// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/request";
import { PersonalSourceManager } from "@/app/sources/personal/components/personal-source-manager";

const api = vi.hoisted(() => ({
  listPersonalSources: vi.fn(),
  createPersonalSource: vi.fn(),
  updatePersonalSource: vi.fn(),
}));
vi.mock("@/api/gerenlaiyuan", () => api);
const profile = {
  id: "profile-1",
  name: "我的订阅",
  source_key: "ed_personal_rss_test",
  revision: 1,
  enabled: false,
  interval_minutes: 30,
  policy_version: 1,
  configuration: {
    kind: "rss",
    feed_url: "https://example.com/feed",
    allowed_hosts: ["example.com"],
  },
};
beforeEach(() => {
  vi.resetAllMocks();
  api.listPersonalSources.mockResolvedValue([]);
  api.createPersonalSource.mockResolvedValue(profile);
});
afterEach(cleanup);

function fill() {
  fireEvent.click(screen.getByRole("button", { name: "新增来源" }));
  fireEvent.change(screen.getByLabelText("来源名称"), {
    target: { value: "我的订阅" },
  });
  fireEvent.change(screen.getByLabelText("订阅地址"), {
    target: { value: "https://example.com/feed" },
  });
}
function submit() {
  fireEvent.submit(screen.getByLabelText("来源名称").closest("form")!);
}

it("loads account sources without operator credentials and creates a disabled RSS with a stable operation", async () => {
  render(<PersonalSourceManager />);
  await screen.findByText("还没有个人来源");
  expect(api.listPersonalSources).toHaveBeenCalledWith();
  expect(screen.queryByLabelText("操作员令牌")).toBeNull();
  fill();
  submit();
  await screen.findByText("来源配置已保存。");
  expect(api.createPersonalSource).toHaveBeenCalledWith(
    expect.objectContaining({
      name: "我的订阅",
      enabled: false,
      expected_revision: 0,
      interval_minutes: 30,
      operation_id: expect.any(String),
      configuration: profile.configuration,
    }),
  );
  expect(screen.getByRole("button", { name: "编辑 我的订阅" })).toBeTruthy();
});

it("preserves failed inputs and locks unknown outcomes until the same operation succeeds", async () => {
  api.createPersonalSource.mockRejectedValueOnce(
    new ApiRequestError({ kind: "timeout", message: "unknown" }),
  );
  render(<PersonalSourceManager />);
  await screen.findByText("还没有个人来源");
  fill();
  submit();
  await screen.findByText(/保存结果尚未确认/);
  expect((screen.getByLabelText("来源名称") as HTMLInputElement).disabled).toBe(
    true,
  );
  expect((screen.getByLabelText("来源名称") as HTMLInputElement).value).toBe(
    "我的订阅",
  );
  const first = api.createPersonalSource.mock.calls[0][0];
  fireEvent.click(screen.getByRole("button", { name: "重试本次保存" }));
  await screen.findByText("来源配置已保存。");
  expect(api.createPersonalSource.mock.calls[1][0]).toEqual(first);
});

it("retains drafts after version conflicts and updates only the original expected revision", async () => {
  api.listPersonalSources.mockResolvedValue([profile]);
  api.updatePersonalSource.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      code: "editorial_version_conflict",
      status: 409,
      message: "conflict",
    }),
  );
  render(<PersonalSourceManager />);
  fireEvent.click(await screen.findByRole("button", { name: "编辑 我的订阅" }));
  fireEvent.change(screen.getByLabelText("来源名称"), {
    target: { value: "修改的名称" },
  });
  submit();
  await screen.findByText(/来源已更新/);
  expect((screen.getByLabelText("来源名称") as HTMLInputElement).value).toBe(
    "修改的名称",
  );
  expect(api.updatePersonalSource).toHaveBeenCalledWith(
    { profile_id: profile.id },
    expect.objectContaining({ expected_revision: 1, name: "修改的名称" }),
  );
});

it("recovers a conflict by rereading and explicitly reopening the latest revision", async () => {
  const latest = { ...profile, revision: 2, name: "其他窗口的名称" };
  api.listPersonalSources
    .mockResolvedValueOnce([profile])
    .mockResolvedValueOnce([latest]);
  api.updatePersonalSource
    .mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        code: "editorial_version_conflict",
        status: 409,
        message: "conflict",
      }),
    )
    .mockResolvedValueOnce({ ...latest, revision: 3, name: "最终名称" });
  render(<PersonalSourceManager />);
  fireEvent.click(await screen.findByRole("button", { name: "编辑 我的订阅" }));
  fireEvent.change(screen.getByLabelText("来源名称"), {
    target: { value: "保留的草稿" },
  });
  submit();
  await screen.findByText(/来源已更新/);
  fireEvent.click(screen.getByRole("button", { name: "重新读取最新来源" }));
  const reopen = await screen.findByRole("button", {
    name: "编辑 其他窗口的名称",
  });
  expect((screen.getByLabelText("来源名称") as HTMLInputElement).value).toBe(
    "保留的草稿",
  );
  fireEvent.click(reopen);
  fireEvent.change(screen.getByLabelText("来源名称"), {
    target: { value: "最终名称" },
  });
  submit();
  await screen.findByText("来源配置已保存。");
  expect(api.updatePersonalSource.mock.calls[1][1]).toEqual(
    expect.objectContaining({ expected_revision: 2, name: "最终名称" }),
  );
});

it.each([401, 403, 503])(
  "supports a recoverable HTTP %s list failure while retaining a draft",
  async (status) => {
    api.listPersonalSources.mockRejectedValueOnce(
      new ApiRequestError({ kind: "http", status, message: "failed" }),
    );
    render(<PersonalSourceManager />);
    fill();
    await screen.findByText("个人来源暂时无法读取");
    expect((screen.getByLabelText("来源名称") as HTMLInputElement).value).toBe(
      "我的订阅",
    );
    fireEvent.click(screen.getByRole("button", { name: "重新读取来源" }));
    await screen.findByText("还没有个人来源");
    expect((screen.getByLabelText("来源名称") as HTMLInputElement).value).toBe(
      "我的订阅",
    );
  },
);

it("keeps loading truthful and ignores a stale list response after a successful create", async () => {
  let resolve!: (items: (typeof profile)[]) => void;
  api.listPersonalSources.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  render(<PersonalSourceManager />);
  expect(screen.getByRole("status", { name: "正在读取个人来源" })).toBeTruthy();
  fill();
  submit();
  await screen.findByText("来源配置已保存。");
  resolve([]);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "编辑 我的订阅" })).toBeTruthy(),
  );
});
