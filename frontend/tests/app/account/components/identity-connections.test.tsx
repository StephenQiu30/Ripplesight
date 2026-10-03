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
  options: vi.fn(),
  send: vi.fn(),
  bind: vi.fn(),
  github: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/api/identity", () => ({
  getLoginOptions: mocks.options,
  sendEmailLinkCode: mocks.send,
  linkIdentityEmail: mocks.bind,
  startGithubLink: mocks.github,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));
vi.mock("sonner", () => ({
  toast: { success: mocks.success, error: mocks.error },
}));
import { IdentityConnections } from "@/app/account/components/identity-connections";
import { ApiRequestError } from "@/request";
const session: HotKeyAPI.IdentitySessionView = {
  user: {
    id: "00000000-0000-4000-8000-000000000002",
    username: "reader",
    email: "old@example.com",
    has_password: true,
    github_connected: false,
  },
  expires_at: "2100-01-01T00:00:00Z",
};
const challenge = {
  challenge_id: "00000000-0000-4000-8000-000000000003",
  expires_at: "2100-01-01T00:00:00Z",
  resend_after_seconds: 60,
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.options.mockResolvedValue({
    password: true,
    email: true,
    github: true,
  });
  mocks.send.mockResolvedValue(challenge);
  mocks.bind.mockResolvedValue({
    ...session,
    user: { ...session.user, email: "new@example.com" },
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
async function openAndSend() {
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "更换邮箱" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole("button", { name: "更换邮箱" }));
  fireEvent.change(screen.getByLabelText("新邮箱"), {
    target: { value: "new@example.com" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "绑定登录邮箱" }));
  await screen.findByLabelText("邮箱验证码");
}
it("verifies the new email through the binding API and refreshes the same account", async () => {
  render(<IdentityConnections session={session} />);
  await openAndSend();
  fireEvent.change(screen.getByLabelText("邮箱验证码"), {
    target: { value: "123456" },
  });
  fireEvent.click(screen.getByRole("button", { name: "验证并绑定" }));
  await screen.findByText("new@example.com");
  expect(mocks.send).toHaveBeenCalledWith(
    { email: "new@example.com" },
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
  expect(mocks.bind).toHaveBeenCalledWith(
    { challenge_id: challenge.challenge_id, code: "123456" },
    expect.anything(),
  );
  expect(mocks.refresh).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("dialog")).toBeNull();
});
it("invalidates a pending email proof when the email changes", async () => {
  render(<IdentityConnections session={session} />);
  await openAndSend();
  fireEvent.change(screen.getByLabelText("新邮箱"), {
    target: { value: "different@example.com" },
  });
  expect(screen.queryByLabelText("邮箱验证码")).toBeNull();
  expect(mocks.bind).not.toHaveBeenCalled();
});
it("keeps identity conflicts in Sonner and leaves the original account unchanged", async () => {
  mocks.bind.mockRejectedValue(
    new ApiRequestError({
      message: "该身份已被占用",
      kind: "http",
      status: 409,
      code: "identity_link_conflict",
    }),
  );
  render(<IdentityConnections session={session} />);
  await openAndSend();
  fireEvent.change(screen.getByLabelText("邮箱验证码"), {
    target: { value: "123456" },
  });
  fireEvent.click(screen.getByRole("button", { name: "验证并绑定" }));
  await waitFor(() => expect(mocks.error).toHaveBeenCalled());
  expect(screen.getByText("old@example.com")).toBeTruthy();
  expect(screen.queryByText("该身份已被占用")).toBeNull();
  expect(mocks.refresh).not.toHaveBeenCalled();
});
it("aborts a dismissed email request and ignores its late response", async () => {
  let finish!: (value: typeof challenge) => void;
  mocks.send.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<IdentityConnections session={session} />);
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "更换邮箱" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole("button", { name: "更换邮箱" }));
  fireEvent.change(screen.getByLabelText("新邮箱"), {
    target: { value: "new@example.com" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "绑定登录邮箱" }));
  const signal = mocks.send.mock.calls[0][1].signal as AbortSignal;
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  await waitFor(() => expect(signal.aborted).toBe(true));
  await act(async () => finish(challenge));
  expect(mocks.success).not.toHaveBeenCalled();
  expect(mocks.bind).not.toHaveBeenCalled();
});
it("starts explicit GitHub connection rather than logging in again", async () => {
  const assign = vi
    .spyOn(window.location, "assign")
    .mockImplementation(() => {});
  mocks.github.mockResolvedValue({
    authorization_url: "https://github.com/login/oauth/authorize?state=test",
  });
  render(<IdentityConnections session={session} />);
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "连接 GitHub" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole("button", { name: "连接 GitHub" }));
  await waitFor(() =>
    expect(assign).toHaveBeenCalledWith(
      "https://github.com/login/oauth/authorize?state=test",
    ),
  );
  expect(mocks.github).toHaveBeenCalledTimes(1);
});
it("displays connected status and removes a one-time callback result", async () => {
  render(
    <IdentityConnections
      session={{
        ...session,
        user: { ...session.user, github_connected: true },
      }}
      githubLinked
    />,
  );
  expect(screen.getByText("已连接")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "连接 GitHub" })).toBeNull();
  await waitFor(() =>
    expect(mocks.replace).toHaveBeenCalledWith("/account", { scroll: false }),
  );
  expect(mocks.success).toHaveBeenCalledTimes(1);
});
