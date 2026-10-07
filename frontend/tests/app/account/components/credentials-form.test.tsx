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
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
  toastInfo: vi.fn(),
  toastDismiss: vi.fn(),
  update: vi.fn(),
  send: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("sonner", () => ({
  toast: {
    error: mocks.toastError,
    success: mocks.toastSuccess,
    info: mocks.toastInfo,
    dismiss: mocks.toastDismiss,
  },
}));
vi.mock("@/api/identity", () => ({
  updateIdentityCredentials: mocks.update,
  sendEmailLoginCode: mocks.send,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));

import { CredentialsForm } from "@/app/account/components/credentials-form";
import { ApiRequestError } from "@/request";

const session: HotKeyAPI.IdentitySessionView = {
  user: {
    id: "00000000-0000-4000-8000-000000000002",
    username: "reader",
    email: "reader@example.com",
    has_password: true,
    github_connected: false,
  },
  expires_at: "2100-01-01T00:00:00Z",
};
const passwordless: HotKeyAPI.IdentitySessionView = {
  ...session,
  user: {
    ...session.user,
    username: "user_random_internal",
    has_password: false,
    github_connected: false,
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.update.mockResolvedValue(session);
  mocks.send.mockResolvedValue({
    challenge_id: "00000000-0000-4000-8000-000000000003",
    expires_at: "2100-01-01T00:00:00Z",
    resend_after_seconds: 60,
  } satisfies HotKeyAPI.EmailChallengeView);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function setPassword(value = "next-test-password") {
  const username = screen.queryByLabelText("用户名") as HTMLInputElement | null;
  if (username && !username.value)
    fireEvent.change(username, { target: { value: "chosen.reader" } });
  fireEvent.change(screen.getByLabelText("新密码"), { target: { value } });
  fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value } });
}
function submit() {
  fireEvent.submit(screen.getByRole("form", { name: "设置登录凭据" }));
}
async function selectEmail() {
  fireEvent.mouseDown(screen.getByRole("tab", { name: "邮箱验证码" }), {
    button: 0,
    ctrlKey: false,
  });
  await screen.findByLabelText("邮箱验证码", { selector: "input" });
}
async function sendAndFillCode() {
  fireEvent.click(screen.getByRole("button", { name: "发送验证码" }));
  await screen.findByText("验证码已发送至当前已验证邮箱。");
  fireEvent.change(screen.getByLabelText("邮箱验证码", { selector: "input" }), {
    target: { value: "123456" },
  });
}

it("changes an existing password through the generated API and keeps the renewed session", async () => {
  render(<CredentialsForm session={session} />);
  setPassword();
  fireEvent.change(screen.getByLabelText("当前密码", { selector: "input" }), {
    target: { value: "old-test-password" },
  });
  submit();
  await waitFor(() =>
    expect(mocks.update).toHaveBeenCalledWith(
      {
        username: "reader",
        password: "next-test-password",
        current_password: "old-test-password",
        challenge_id: undefined,
        code: undefined,
      },
      { signal: expect.any(AbortSignal) },
    ),
  );
  await waitFor(() =>
    expect(mocks.toastSuccess).toHaveBeenCalledWith(
      expect.stringContaining("密码已保存。下次可使用邮箱或用户名和密码登录"),
    ),
  );
  expect(mocks.replace).not.toHaveBeenCalled();
  expect(mocks.refresh).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText("新密码")).toHaveProperty("value", "");
  expect(
    screen.getByLabelText("当前密码", { selector: "input" }),
  ).toHaveProperty("value", "");
});

it("sets a chosen username and first password after recent verification", async () => {
  mocks.update.mockResolvedValue({
    ...passwordless,
    user: { ...passwordless.user, has_password: true },
  } satisfies HotKeyAPI.IdentitySessionView);
  render(
    <CredentialsForm
      session={passwordless}
      initialSetup
      returnTo="/jobs/job-1?state=failed"
    />,
  );
  expect(
    screen.getByRole("heading", { name: "设置用户名和密码" }),
  ).toBeTruthy();
  expect(screen.getByText("已验证邮箱：reader@example.com")).toBeTruthy();
  expect(screen.getByLabelText("用户名")).toHaveProperty("value", "");
  expect(screen.queryByLabelText("当前密码", { selector: "input" })).toBeNull();
  expect(screen.queryByText("user_random_internal")).toBeNull();
  setPassword();
  submit();
  await waitFor(() =>
    expect(mocks.update).toHaveBeenCalledWith(
      {
        username: "chosen.reader",
        password: "next-test-password",
        current_password: undefined,
        challenge_id: undefined,
        code: undefined,
      },
      { signal: expect.any(AbortSignal) },
    ),
  );
  expect(mocks.replace).toHaveBeenCalledWith("/jobs/job-1?state=failed");
  expect(mocks.refresh).toHaveBeenCalledTimes(1);
});

it("sanitizes an unsafe original destination when initial setup completes", async () => {
  render(
    <CredentialsForm
      session={passwordless}
      initialSetup
      returnTo="//attacker.invalid"
    />,
  );
  setPassword();
  submit();
  await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/topics"));
});

it("lets an existing email-only user set a password from account settings and stays there", async () => {
  render(<CredentialsForm session={passwordless} />);
  expect(screen.getByRole("button", { name: "保存密码" })).toBeTruthy();
  setPassword();
  submit();
  await waitFor(() =>
    expect(mocks.toastSuccess).toHaveBeenCalledWith(
      expect.stringContaining("密码已保存。下次可使用邮箱或用户名和密码登录"),
    ),
  );
  expect(mocks.replace).not.toHaveBeenCalled();
  expect(mocks.refresh).toHaveBeenCalledTimes(1);
});

it("rejects a mismatched password confirmation before any mutation", async () => {
  render(<CredentialsForm session={passwordless} initialSetup />);
  setPassword();
  fireEvent.change(screen.getByLabelText("确认新密码"), {
    target: { value: "different-test-password" },
  });
  submit();
  await waitFor(() =>
    expect(mocks.toastError).toHaveBeenCalledWith("两次输入的新密码不一致。"),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(mocks.update).not.toHaveBeenCalled();
});

it.each(["too-short", "a".repeat(129)])(
  "rejects a password outside the allowed length",
  async (password) => {
    render(<CredentialsForm session={passwordless} />);
    setPassword(password);
    submit();
    await waitFor(() =>
      expect(mocks.toastError).toHaveBeenCalledWith("密码需要 12–128 个字符。"),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(mocks.update).not.toHaveBeenCalled();
  },
);

it("requires proof for an account with an existing password", async () => {
  render(<CredentialsForm session={session} />);
  setPassword();
  submit();
  await waitFor(() =>
    expect(mocks.toastError).toHaveBeenCalledWith(
      "请输入当前密码，或使用邮箱验证码验证。",
    ),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(mocks.update).not.toHaveBeenCalled();
});

it("uses only the current verified email for an existing password change", async () => {
  render(<CredentialsForm session={session} />);
  setPassword();
  await selectEmail();
  await sendAndFillCode();
  expect(mocks.send).toHaveBeenCalledWith(
    { email: "reader@example.com" },
    { signal: expect.any(AbortSignal) },
  );
  submit();
  await waitFor(() =>
    expect(mocks.update).toHaveBeenCalledWith(
      {
        username: "reader",
        password: "next-test-password",
        current_password: undefined,
        challenge_id: "00000000-0000-4000-8000-000000000003",
        code: "123456",
      },
      { signal: expect.any(AbortSignal) },
    ),
  );
});

it("recovers expired recent verification by requesting a fresh code for the bound mailbox", async () => {
  mocks.update.mockRejectedValueOnce(
    new ApiRequestError({
      kind: "http",
      status: 403,
      code: "credentials_verification_required",
      message: "verification required",
    }),
  );
  render(
    <CredentialsForm
      session={passwordless}
      initialSetup
      returnTo="/content?state=unread"
    />,
  );
  setPassword();
  submit();
  await waitFor(() =>
    expect(mocks.toastError).toHaveBeenCalledWith(
      "登录验证已过期，请重新验证下方已绑定邮箱后设置密码。",
    ),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.queryByLabelText("当前密码", { selector: "input" })).toBeNull();
  expect(screen.getByLabelText("新密码")).toHaveProperty(
    "value",
    "next-test-password",
  );
  expect(mocks.send).not.toHaveBeenCalled();
  await sendAndFillCode();
  submit();
  await waitFor(() => expect(mocks.update).toHaveBeenCalledTimes(2));
  expect(mocks.update.mock.calls[1][0]).toEqual({
    username: "chosen.reader",
    password: "next-test-password",
    current_password: undefined,
    challenge_id: "00000000-0000-4000-8000-000000000003",
    code: "123456",
  });
  expect(mocks.replace).toHaveBeenCalledWith("/content?state=unread");
});

it("keeps a failed code send on the setup form and allows a deliberate retry", async () => {
  mocks.send.mockRejectedValueOnce(
    new ApiRequestError({ kind: "network", message: "offline" }),
  );
  render(<CredentialsForm session={passwordless} initialSetup />);
  fireEvent.click(screen.getByRole("button", { name: "重新验证邮箱" }));
  fireEvent.click(screen.getByRole("button", { name: "发送验证码" }));
  await waitFor(() =>
    expect(mocks.toastError).toHaveBeenCalledWith(
      "暂时无法连接服务，请稍后重试。",
    ),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  await sendAndFillCode();
  expect(mocks.send).toHaveBeenCalledTimes(2);
  expect(mocks.update).not.toHaveBeenCalled();
});

it("keeps an incorrect mailbox code editable so setup can retry without losing its password or destination", async () => {
  mocks.update.mockRejectedValueOnce(
    new ApiRequestError({
      kind: "http",
      status: 401,
      code: "invalid_email_code",
      message: "invalid code",
    }),
  );
  render(
    <CredentialsForm
      session={passwordless}
      initialSetup
      returnTo="/events?kind=latest"
    />,
  );
  setPassword();
  fireEvent.click(screen.getByRole("button", { name: "重新验证邮箱" }));
  await sendAndFillCode();
  submit();
  await waitFor(() =>
    expect(mocks.toastError).toHaveBeenCalledWith(
      "验证未通过，请检查输入后重试。",
    ),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByLabelText("新密码")).toHaveProperty(
    "value",
    "next-test-password",
  );
  fireEvent.change(screen.getByLabelText("邮箱验证码", { selector: "input" }), {
    target: { value: "654321" },
  });
  submit();
  await waitFor(() =>
    expect(mocks.replace).toHaveBeenCalledWith("/events?kind=latest"),
  );
  expect(mocks.update.mock.calls[1][0].code).toBe("654321");
  expect(mocks.send).toHaveBeenCalledTimes(1);
});

it("enforces code resend cooldown and blocks an expired code before saving", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-02T04:00:00Z"));
  mocks.send.mockResolvedValue({
    challenge_id: "00000000-0000-4000-8000-000000000003",
    expires_at: "2026-10-02T04:05:00Z",
    resend_after_seconds: 60,
  } satisfies HotKeyAPI.EmailChallengeView);
  render(<CredentialsForm session={passwordless} initialSetup />);
  setPassword();
  fireEvent.click(screen.getByRole("button", { name: "重新验证邮箱" }));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "发送验证码" }));
  });
  expect(
    screen.getByRole("button", { name: "60 秒后可重新发送" }),
  ).toHaveProperty("disabled", true);
  await act(async () => {
    vi.advanceTimersByTime(60_000);
  });
  expect(screen.getByRole("button", { name: "重新发送验证码" })).toHaveProperty(
    "disabled",
    false,
  );
  fireEvent.change(screen.getByLabelText("邮箱验证码", { selector: "input" }), {
    target: { value: "123456" },
  });
  await act(async () => {
    vi.advanceTimersByTime(241_000);
  });
  expect(screen.getByText("验证码已过期，请重新发送。")).toBeTruthy();
  expect(
    screen.getByLabelText("邮箱验证码", { selector: "input" }),
  ).toHaveProperty("disabled", true);
  submit();
  expect(mocks.toastError).toHaveBeenCalledWith(
    "请发送并填写有效的邮箱验证码。",
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(mocks.update).not.toHaveBeenCalled();
});

it("keeps save busy without a cancellation button and ignores completion after leaving", async () => {
  let finish!: (value: HotKeyAPI.IdentitySessionView) => void;
  mocks.update.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const view = render(<CredentialsForm session={passwordless} initialSetup />);
  setPassword();
  submit();
  await waitFor(() => expect(mocks.update).toHaveBeenCalled());
  expect(screen.getByRole("button", { name: "正在保存…" })).toHaveProperty(
    "disabled",
    true,
  );
  expect(screen.queryByRole("button", { name: "取消" })).toBeNull();
  submit();
  expect(mocks.update).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(mocks.update.mock.calls[0][1].signal.aborted).toBe(true);
  await act(async () => {
    finish(session);
  });
  expect(mocks.toastInfo).not.toHaveBeenCalled();
  expect(mocks.toastSuccess).not.toHaveBeenCalled();
  expect(mocks.toastError).not.toHaveBeenCalled();
  expect(mocks.replace).not.toHaveBeenCalled();
  expect(mocks.refresh).not.toHaveBeenCalled();
});

it("requires a chosen username and preserves input after a name conflict", async () => {
  render(<CredentialsForm session={passwordless} initialSetup />);
  setPassword();
  fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "" } });
  submit();
  expect(mocks.update).not.toHaveBeenCalled();
  mocks.update.mockRejectedValueOnce(
    new ApiRequestError({
      kind: "http",
      status: 409,
      code: "username_unavailable",
      message: "用户名已被使用",
    }),
  );
  fireEvent.change(screen.getByLabelText("用户名"), {
    target: { value: "taken.reader" },
  });
  submit();
  await waitFor(() =>
    expect(mocks.toastError).toHaveBeenCalledWith("用户名已被使用"),
  );
  expect(mocks.replace).not.toHaveBeenCalled();
  expect(screen.getByLabelText("新密码")).toHaveProperty(
    "value",
    "next-test-password",
  );
  fireEvent.change(screen.getByLabelText("用户名"), {
    target: { value: "chosen.reader" },
  });
  submit();
  await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/topics"));
});
