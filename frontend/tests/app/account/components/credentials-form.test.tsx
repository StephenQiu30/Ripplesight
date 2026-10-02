// @vitest-environment happy-dom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
  send: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/api/identity", () => ({
  updateIdentityCredentials: mocks.update,
  sendEmailLoginCode: mocks.send,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));

import { CredentialsForm } from "@/app/account/components/credentials-form";

const session: HotKeyAPI.IdentitySessionView = {
  user: {
    id: "00000000-0000-4000-8000-000000000002",
    username: "reader",
    email: "reader@example.com",
  },
  expires_at: "2100-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.update.mockResolvedValue(undefined);
  mocks.send.mockResolvedValue({
    challenge_id: "00000000-0000-4000-8000-000000000003",
    expires_at: "2100-01-01T00:00:00Z",
    resend_after_seconds: 60,
  } satisfies HotKeyAPI.EmailChallengeView);
});
afterEach(cleanup);

function setPassword() {
  fireEvent.change(screen.getByLabelText("新密码"), {
    target: { value: "next-test-password" },
  });
  fireEvent.change(screen.getByLabelText("确认新密码"), {
    target: { value: "next-test-password" },
  });
}

it("updates through the generated credentials API and requires a fresh login", async () => {
  render(<CredentialsForm session={session} />);
  setPassword();
  fireEvent.change(screen.getByLabelText("当前密码", { selector: "input" }), {
    target: { value: "old-test-password" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "设置登录凭据" }));
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
  expect(mocks.replace).toHaveBeenCalledWith("/login");
  expect(mocks.refresh).toHaveBeenCalledTimes(1);
});

it("rejects a mismatched password confirmation before a server mutation", async () => {
  render(<CredentialsForm session={session} />);
  setPassword();
  fireEvent.change(screen.getByLabelText("确认新密码"), {
    target: { value: "different-test-password" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "设置登录凭据" }));
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    "两次输入的新密码不一致。",
  );
  expect(mocks.update).not.toHaveBeenCalled();
});

it("uses only the current verified email for credentials confirmation", async () => {
  render(<CredentialsForm session={session} />);
  setPassword();
  fireEvent.mouseDown(screen.getByRole("tab", { name: "邮箱验证码" }), {
    button: 0,
    ctrlKey: false,
  });
  fireEvent.click(screen.getByRole("button", { name: "发送验证码" }));
  await screen.findByText("验证码已发送至当前已验证邮箱。");
  expect(mocks.send).toHaveBeenCalledWith(
    { email: "reader@example.com" },
    { signal: expect.any(AbortSignal) },
  );
  fireEvent.change(screen.getByLabelText("邮箱验证码", { selector: "input" }), {
    target: { value: "123456" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "设置登录凭据" }));
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

it("allows a recent OAuth account to set its first password without inventing an existing password", async () => {
  render(
    <CredentialsForm
      session={{ ...session, user: { ...session.user, email: null } }}
    />,
  );
  setPassword();
  fireEvent.submit(screen.getByRole("form", { name: "设置登录凭据" }));
  await waitFor(() => expect(mocks.update).toHaveBeenCalled());
  expect(mocks.update.mock.calls[0]?.[0].current_password).toBeUndefined();
  expect(screen.queryByRole("tab", { name: "邮箱验证码" })).toBeNull();
});
