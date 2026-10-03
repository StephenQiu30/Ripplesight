// @vitest-environment happy-dom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  profile: vi.fn(),
  avatar: vi.fn(),
  read: vi.fn(),
  refresh: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock("@/api/identity", () => ({
  updateIdentityProfile: mocks.profile,
  uploadIdentityAvatar: mocks.avatar,
  getIdentityAvatar: mocks.read,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mocks.refresh }),
}));
vi.mock("sonner", () => ({
  toast: { success: mocks.success, error: mocks.error },
}));
vi.mock("@/app/account/components/identity-connections", () => ({
  IdentityConnections: () => null,
}));
vi.mock("@/app/account/components/credentials-form", () => ({
  CredentialsForm: () => <p>密码表单</p>,
}));
import { AccountSettings } from "@/app/account/components/account-settings";
import { ApiRequestError } from "@/request";

const session: HotKeyAPI.IdentitySessionView = {
  user: {
    id: "owner",
    username: "reader",
    email: "reader@example.com",
    has_password: true,
    github_connected: false,
  },
  expires_at: "2100-01-01T00:00:00Z",
};
beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(cleanup);

it("saves a username independently of password and updates the profile summary", async () => {
  mocks.profile.mockResolvedValue({
    ...session,
    user: { ...session.user, username: "reader.new" },
  });
  render(<AccountSettings session={session} />);
  fireEvent.click(screen.getByRole("button", { name: "编辑资料" }));
  fireEvent.change(screen.getByLabelText("用户名"), {
    target: { value: "reader.new" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "编辑个人资料" }));
  await waitFor(() =>
    expect(mocks.profile).toHaveBeenCalledWith(
      { username: "reader.new" },
      { signal: expect.any(AbortSignal) },
    ),
  );
  expect(mocks.success).toHaveBeenCalledWith("个人资料已保存。");
  expect(mocks.refresh).toHaveBeenCalledTimes(1);
  expect(screen.getAllByText("reader.new").length).toBe(2);
  expect(mocks.avatar).not.toHaveBeenCalled();
});

it("rejects oversized and unsupported files before reading or uploading", () => {
  render(<AccountSettings session={session} />);
  const input = screen.getByLabelText("上传头像文件");
  fireEvent.change(input, {
    target: {
      files: [new File(["<svg/>"], "avatar.svg", { type: "image/svg+xml" })],
    },
  });
  fireEvent.change(input, {
    target: {
      files: [
        new File([new Uint8Array(2 * 1024 * 1024 + 1)], "large.png", {
          type: "image/png",
        }),
      ],
    },
  });
  expect(mocks.error).toHaveBeenCalledTimes(2);
  expect(mocks.avatar).not.toHaveBeenCalled();
});

it("uploads file bytes through the generated API and does not alter the username", async () => {
  mocks.avatar.mockResolvedValue({
    ...session,
    user: { ...session.user, avatar_sha256: "a".repeat(64) },
  });
  mocks.read.mockResolvedValue(new Blob(["png"], { type: "image/png" }));
  render(<AccountSettings session={session} />);
  fireEvent.change(screen.getByLabelText("上传头像文件"), {
    target: {
      files: [new File(["image-bytes"], "avatar.png", { type: "image/png" })],
    },
  });
  await waitFor(() =>
    expect(mocks.avatar).toHaveBeenCalledWith(
      { mime: "image/png", data_base64: "aW1hZ2UtYnl0ZXM=" },
      { signal: expect.any(AbortSignal) },
    ),
  );
  await screen.findByRole("button", { name: "更换头像" });
  expect(mocks.success).toHaveBeenCalledWith("头像已更新。");
  expect(mocks.profile).not.toHaveBeenCalled();
});

it("keeps the existing avatar after an upload failure and permits retry", async () => {
  mocks.avatar.mockRejectedValue(
    new ApiRequestError({ kind: "network", message: "offline" }),
  );
  mocks.read.mockResolvedValue(new Blob(["png"], { type: "image/png" }));
  render(
    <AccountSettings
      session={{
        ...session,
        user: { ...session.user, avatar_sha256: "b".repeat(64) },
      }}
    />,
  );
  fireEvent.change(screen.getByLabelText("上传头像文件"), {
    target: {
      files: [new File(["image"], "avatar.png", { type: "image/png" })],
    },
  });
  await waitFor(() =>
    expect(mocks.error).toHaveBeenCalledWith("暂时无法连接服务，请稍后重试。"),
  );
  expect(screen.getByRole("button", { name: "更换头像" })).toHaveProperty(
    "disabled",
    false,
  );
  expect(mocks.success).not.toHaveBeenCalled();
  expect(mocks.refresh).not.toHaveBeenCalled();
});

it("aborts a pending upload on departure and ignores late completion", async () => {
  let finish!: (value: HotKeyAPI.IdentitySessionView) => void;
  mocks.avatar.mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const view = render(<AccountSettings session={session} />);
  fireEvent.change(screen.getByLabelText("上传头像文件"), {
    target: {
      files: [new File(["image"], "avatar.png", { type: "image/png" })],
    },
  });
  await waitFor(() => expect(mocks.avatar).toHaveBeenCalledTimes(1));
  view.unmount();
  expect(mocks.avatar.mock.calls[0][1].signal.aborted).toBe(true);
  await act(async () => finish(session));
  expect(mocks.refresh).not.toHaveBeenCalled();
  expect(mocks.success).not.toHaveBeenCalled();
});
