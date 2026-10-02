// @vitest-environment happy-dom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  options: vi.fn(),
  password: vi.fn(),
  send: vi.fn(),
  verify: vi.fn(),
  github: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("@/api/identity", () => ({
  getLoginOptions: mocks.options,
  createIdentitySession: mocks.password,
  sendEmailLoginCode: mocks.send,
  verifyEmailLoginCode: mocks.verify,
  startGithubLogin: mocks.github,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));

import { LoginForm } from "@/app/login/components/login-form";
import { ApiRequestError } from "@/request";

beforeEach(() => {
  vi.clearAllMocks();
  mocks.options.mockResolvedValue({
    password: true,
    github: true,
    email: true,
  } satisfies HotKeyAPI.LoginOptionsView);
  mocks.password.mockResolvedValue({});
  mocks.verify.mockResolvedValue({});
  mocks.send.mockResolvedValue({
    challenge_id: "00000000-0000-4000-8000-000000000001",
    expires_at: "2100-01-01T00:00:00Z",
    resend_after_seconds: 60,
  } satisfies HotKeyAPI.EmailChallengeView);
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function selectEmail() {
  fireEvent.mouseDown(await screen.findByRole("tab", { name: "邮箱验证码" }), {
    button: 0,
    ctrlKey: false,
  });
  await screen.findByLabelText("邮箱");
}

describe("LoginForm", () => {
  it("starts GitHub with the generated operation and then navigates to the returned authorization URL", async () => {
    const navigate = vi
      .spyOn(window.location, "assign")
      .mockImplementation(() => {});
    mocks.github.mockResolvedValue({
      authorization_url:
        "https://github.com/login/oauth/authorize?state=opaque",
    } satisfies HotKeyAPI.GithubAuthorizationView);
    render(<LoginForm returnTo="/content" />);
    fireEvent.mouseDown(await screen.findByRole("tab", { name: "GitHub" }), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(
      await screen.findByRole("button", { name: "使用 GitHub 登录" }),
    );
    await waitFor(() =>
      expect(mocks.github).toHaveBeenCalledWith(
        { return_to: "/content" },
        { signal: expect.any(AbortSignal) },
      ),
    );
    expect(navigate).toHaveBeenCalledWith(
      "https://github.com/login/oauth/authorize?state=opaque",
    );
  });

  it("logs in with the generated API and returns to the original workspace page", async () => {
    render(<LoginForm returnTo="/jobs/job-1?state=failed" />);
    fireEvent.change(await screen.findByLabelText("用户名"), {
      target: { value: "reader" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "test-password-only" },
    });
    fireEvent.submit(screen.getByRole("form", { name: "账号密码登录" }));
    await waitFor(() =>
      expect(mocks.password).toHaveBeenCalledWith(
        { username: "reader", password: "test-password-only" },
        { signal: expect.any(AbortSignal) },
      ),
    );
    expect(mocks.replace).toHaveBeenCalledWith("/jobs/job-1?state=failed");
    expect(mocks.refresh).toHaveBeenCalledTimes(1);
  });

  it("keeps invalid credentials on the login form and allows a deliberate retry", async () => {
    mocks.password.mockRejectedValueOnce(
      new ApiRequestError({ kind: "http", status: 401, message: "验证失败" }),
    );
    render(<LoginForm returnTo="//evil.example" />);
    await screen.findByLabelText("用户名");
    fireEvent.submit(screen.getByRole("form", { name: "账号密码登录" }));
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "验证未通过，请检查输入后重试。",
    );
    expect(mocks.replace).not.toHaveBeenCalled();
    fireEvent.submit(screen.getByRole("form", { name: "账号密码登录" }));
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/topics"));
  });

  it("sends and verifies the actual email challenge without exposing its identifier", async () => {
    render(<LoginForm returnTo="/topics" />);
    await selectEmail();
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "reader@example.com" },
    });
    fireEvent.submit(screen.getByRole("form", { name: "邮箱验证码登录" }));
    fireEvent.change(await screen.findByLabelText("验证码"), {
      target: { value: "123456" },
    });
    expect(mocks.send).toHaveBeenCalledWith(
      { email: "reader@example.com" },
      { signal: expect.any(AbortSignal) },
    );
    expect(
      (
        screen.getByRole("button", {
          name: /秒后可重新发送/,
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(
      screen.queryByText("00000000-0000-4000-8000-000000000001"),
    ).toBeNull();
    fireEvent.submit(screen.getByRole("form", { name: "邮箱验证码登录" }));
    await waitFor(() =>
      expect(mocks.verify).toHaveBeenCalledWith(
        {
          challenge_id: "00000000-0000-4000-8000-000000000001",
          code: "123456",
        },
        { signal: expect.any(AbortSignal) },
      ),
    );
    expect(mocks.replace).toHaveBeenCalledWith("/topics");
  });

  it("clears a previously sent challenge when the destination email changes", async () => {
    render(<LoginForm returnTo="/topics" />);
    await selectEmail();
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "first@example.com" },
    });
    fireEvent.submit(screen.getByRole("form", { name: "邮箱验证码登录" }));
    await screen.findByLabelText("验证码");
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "second@example.com" },
    });
    expect(screen.queryByLabelText("验证码")).toBeNull();
    fireEvent.submit(screen.getByRole("form", { name: "邮箱验证码登录" }));
    await waitFor(() =>
      expect(mocks.send).toHaveBeenLastCalledWith(
        { email: "second@example.com" },
        { signal: expect.any(AbortSignal) },
      ),
    );
    expect(mocks.verify).not.toHaveBeenCalled();
  });

  it("reports a provider that is not configured without starting a fake login", async () => {
    mocks.options.mockResolvedValue({
      password: true,
      github: false,
      email: false,
    });
    render(<LoginForm returnTo="/topics" />);
    fireEvent.mouseDown(await screen.findByRole("tab", { name: "GitHub" }), {
      button: 0,
      ctrlKey: false,
    });
    expect(
      await screen.findByText("GitHub 登录尚未配置，请选择其他登录方式。"),
    ).toBeTruthy();
    expect(mocks.github).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: "使用 GitHub 登录" }),
    ).toBeNull();
  });

  it("retries login options after a network failure", async () => {
    mocks.options.mockRejectedValueOnce(
      new ApiRequestError({ kind: "network", message: "offline" }),
    );
    render(<LoginForm returnTo="/topics" />);
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    await screen.findByLabelText("用户名");
    expect(mocks.options).toHaveBeenCalledTimes(2);
  });
});
