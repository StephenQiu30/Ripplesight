// @vitest-environment happy-dom

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
  toastInfo: vi.fn(),
  toastDismiss: vi.fn(),
  options: vi.fn(),
  password: vi.fn(),
  send: vi.fn(),
  verify: vi.fn(),
  github: vi.fn(),
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
import { StrictMode } from "react";

beforeEach(() => {
  vi.clearAllMocks();
  mocks.options.mockResolvedValue({
    password: true,
    github: true,
    email: true,
  } satisfies HotKeyAPI.LoginOptionsView);
  mocks.password.mockResolvedValue({});
  mocks.verify.mockResolvedValue({
    user: {
      id: "00000000-0000-4000-8000-000000000002",
      username: "reader",
      email: "reader@example.com",
      has_password: true,
      github_connected: false,
    },
    expires_at: "2100-01-01T00:00:00Z",
  } satisfies HotKeyAPI.IdentitySessionView);
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
  fireEvent.click(
    await screen.findByRole("button", { name: "使用邮箱验证码登录" }),
  );
  await screen.findByLabelText("邮箱");
}

describe("LoginForm", () => {
  it.each([
    [{ password: true, email: true, github: false }, "账号密码登录"],
    [{ password: false, email: true, github: false }, "邮箱验证码登录"],
    [{ password: false, email: false, github: true }, "其他登录方式"],
  ] satisfies [HotKeyAPI.LoginOptionsView, string][])(
    "retains the loading region and static content when providers become ready: %s",
    async (options, formName) => {
      let finishOptions!: (value: HotKeyAPI.LoginOptionsView) => void;
      mocks.options.mockReturnValueOnce(
        new Promise((resolve) => {
          finishOptions = resolve;
        }),
      );
      render(<LoginForm returnTo="/topics" />);
      const heading = screen.getByRole("heading", { name: "登录" });
      const terms = screen.getByRole("link", { name: "使用条款" });
      const loading = screen.getByRole("status", { name: "正在读取登录方式" });
      const region = loading.parentElement!;
      expect(region.getAttribute("aria-busy")).toBe("true");
      expect(screen.queryByRole("textbox")).toBeNull();
      expect(screen.queryByRole("button")).toBeNull();
      await act(async () => finishOptions(options));
      expect(
        screen.queryByRole("status", { name: "正在读取登录方式" }),
      ).toBeNull();
      expect(region.getAttribute("aria-busy")).toBe("false");
      expect(screen.getByRole("heading", { name: "登录" })).toBe(heading);
      expect(screen.getByRole("link", { name: "使用条款" })).toBe(terms);
      expect(
        screen.getByRole(options.password || options.email ? "form" : "group", {
          name: formName,
        }).parentElement,
      ).toBe(region);
      expect(mocks.toastError).not.toHaveBeenCalled();
    },
  );

  it("reports an OAuth callback failure once even with StrictMode and rerenders", async () => {
    const view = render(
      <StrictMode>
        <LoginForm returnTo="/topics" oauthFailed />
      </StrictMode>,
    );
    await screen.findByLabelText("邮箱或用户名");
    expect(mocks.toastError).toHaveBeenCalledExactlyOnceWith(
      "GitHub 登录未完成，请重新尝试。",
      { id: expect.any(String) },
    );
    view.rerender(
      <StrictMode>
        <LoginForm returnTo="/content" oauthFailed />
      </StrictMode>,
    );
    expect(mocks.toastError).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("shows password login with other login methods as buttons instead of tabs", async () => {
    render(<LoginForm returnTo="/topics" />);
    await screen.findByRole("form", { name: "账号密码登录" });
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    expect(
      screen.getByRole("button", { name: "使用邮箱验证码登录" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "使用 GitHub 登录" }),
    ).toBeTruthy();
  });

  it("starts GitHub with the generated operation and then navigates to the returned authorization URL", async () => {
    const navigate = vi
      .spyOn(window.location, "assign")
      .mockImplementation(() => {});
    mocks.github.mockResolvedValue({
      authorization_url:
        "https://github.com/login/oauth/authorize?state=opaque",
    } satisfies HotKeyAPI.GithubAuthorizationView);
    render(<LoginForm returnTo="/content" />);
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
    fireEvent.change(await screen.findByLabelText("邮箱或用户名"), {
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

  it("lets the user reveal and hide the password without changing it", async () => {
    render(<LoginForm returnTo="/topics" />);
    const password = (await screen.findByLabelText("密码")) as HTMLInputElement;
    fireEvent.change(password, { target: { value: "test-password-only" } });
    expect(password.type).toBe("password");
    fireEvent.click(screen.getByRole("button", { name: "显示密码" }));
    expect(password.type).toBe("text");
    expect(password.value).toBe("test-password-only");
    fireEvent.click(screen.getByRole("button", { name: "隐藏密码" }));
    expect(password.type).toBe("password");
    expect(password.value).toBe("test-password-only");
    expect(mocks.password).not.toHaveBeenCalled();
  });

  it("accepts an email in the password login field while preserving the generated API payload", async () => {
    render(<LoginForm returnTo="/topics" />);
    const identifier = (await screen.findByLabelText(
      "邮箱或用户名",
    )) as HTMLInputElement;
    expect(identifier.maxLength).toBe(254);
    expect(identifier.getAttribute("autocapitalize")).toBe("none");
    fireEvent.change(identifier, { target: { value: "reader@example.com" } });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "test-password-only" },
    });
    fireEvent.submit(screen.getByRole("form", { name: "账号密码登录" }));
    await waitFor(() =>
      expect(mocks.password).toHaveBeenCalledWith(
        { username: "reader@example.com", password: "test-password-only" },
        { signal: expect.any(AbortSignal) },
      ),
    );
    expect(mocks.replace).toHaveBeenCalledWith("/topics");
  });

  it("keeps invalid credentials on the login form and allows a deliberate retry", async () => {
    mocks.password.mockRejectedValueOnce(
      new ApiRequestError({ kind: "http", status: 401, message: "验证失败" }),
    );
    render(<LoginForm returnTo="//evil.example" />);
    await screen.findByLabelText("邮箱或用户名");
    fireEvent.submit(screen.getByRole("form", { name: "账号密码登录" }));
    await waitFor(() =>
      expect(mocks.toastError).toHaveBeenCalledWith(
        "验证未通过，请检查输入后重试。",
        { id: expect.any(String) },
      ),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(mocks.replace).not.toHaveBeenCalled();
    fireEvent.submit(screen.getByRole("form", { name: "账号密码登录" }));
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/topics"));
  });

  it("switches forms without submitting, preserves entered values, and clears the previous error", async () => {
    mocks.password.mockRejectedValueOnce(
      new ApiRequestError({ kind: "http", status: 401, message: "验证失败" }),
    );
    render(<LoginForm returnTo="/topics" />);
    fireEvent.change(await screen.findByLabelText("邮箱或用户名"), {
      target: { value: "reader" },
    });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "test-password-only" },
    });
    fireEvent.submit(screen.getByRole("form", { name: "账号密码登录" }));
    await waitFor(() => expect(mocks.toastError).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
    await selectEmail();
    expect(document.activeElement).toBe(screen.getByLabelText("邮箱"));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("form", { name: "账号密码登录" })).toBeNull();
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "reader@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "使用账号密码登录" }));
    expect(
      (await screen.findByLabelText("邮箱或用户名")) as HTMLInputElement,
    ).toHaveProperty("value", "reader");
    expect(document.activeElement).toBe(screen.getByLabelText("邮箱或用户名"));
    expect(screen.getByLabelText("密码")).toHaveProperty(
      "value",
      "test-password-only",
    );
    await selectEmail();
    expect(screen.getByLabelText("邮箱")).toHaveProperty(
      "value",
      "reader@example.com",
    );
    expect(mocks.password).toHaveBeenCalledTimes(1);
    expect(mocks.send).not.toHaveBeenCalled();
    expect(mocks.github).not.toHaveBeenCalled();
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

  it.each([
    ["/jobs/job-1?state=failed", "/jobs/job-1?state=failed"],
    ["//attacker.invalid", "/topics"],
  ])(
    "takes an email account without a password to setup and preserves a safe original destination",
    async (returnTo, expected) => {
      mocks.verify.mockResolvedValue({
        user: {
          id: "00000000-0000-4000-8000-000000000002",
          username: "user_random_internal",
          email: "reader@example.com",
          has_password: false,
          github_connected: false,
        },
        expires_at: "2100-01-01T00:00:00Z",
      } satisfies HotKeyAPI.IdentitySessionView);
      render(<LoginForm returnTo={returnTo} />);
      await selectEmail();
      fireEvent.change(screen.getByLabelText("邮箱"), {
        target: { value: "reader@example.com" },
      });
      fireEvent.submit(screen.getByRole("form", { name: "邮箱验证码登录" }));
      fireEvent.change(await screen.findByLabelText("验证码"), {
        target: { value: "123456" },
      });
      fireEvent.submit(screen.getByRole("form", { name: "邮箱验证码登录" }));
      await waitFor(() =>
        expect(mocks.replace).toHaveBeenCalledWith(
          `/account?setup=1&returnTo=${encodeURIComponent(expected)}`,
        ),
      );
      expect(mocks.refresh).toHaveBeenCalledTimes(1);
    },
  );

  it("disables unavailable providers and never calls their login operations", async () => {
    mocks.options.mockResolvedValue({
      password: true,
      github: false,
      email: false,
    });
    render(<LoginForm returnTo="/topics" />);
    const github = (await screen.findByRole("button", {
      name: "使用 GitHub 登录",
    })) as HTMLButtonElement;
    const email = screen.getByRole("button", {
      name: "使用邮箱验证码登录",
    }) as HTMLButtonElement;
    expect(github.disabled).toBe(true);
    expect(email.disabled).toBe(true);
    expect(screen.getByText("GitHub 登录尚未配置。")).toBeTruthy();
    expect(screen.getByText("邮箱验证码登录尚未配置。")).toBeTruthy();
    fireEvent.click(github);
    fireEvent.click(email);
    expect(mocks.github).not.toHaveBeenCalled();
    expect(mocks.send).not.toHaveBeenCalled();
    expect(screen.getByRole("form", { name: "账号密码登录" })).toBeTruthy();
  });

  it("starts with email when password login is unavailable", async () => {
    mocks.options.mockResolvedValue({
      password: false,
      github: true,
      email: true,
    } satisfies HotKeyAPI.LoginOptionsView);
    render(<LoginForm returnTo="/topics" />);
    await screen.findByRole("form", { name: "邮箱验证码登录" });
    expect(screen.queryByLabelText("邮箱或用户名")).toBeNull();
    expect(screen.queryByRole("tablist")).toBeNull();
    const password = screen.getByRole("button", {
      name: "使用账号密码登录",
    }) as HTMLButtonElement;
    expect(password.disabled).toBe(true);
    expect(mocks.password).not.toHaveBeenCalled();
  });

  it("still starts GitHub directly when neither credential form is available", async () => {
    const navigate = vi
      .spyOn(window.location, "assign")
      .mockImplementation(() => {});
    mocks.options.mockResolvedValue({
      password: false,
      github: true,
      email: false,
    } satisfies HotKeyAPI.LoginOptionsView);
    mocks.github.mockResolvedValue({
      authorization_url:
        "https://github.com/login/oauth/authorize?state=opaque",
    } satisfies HotKeyAPI.GithubAuthorizationView);
    render(<LoginForm returnTo="/topics" />);
    const github = await screen.findByRole("button", {
      name: "使用 GitHub 登录",
    });
    expect(screen.queryByRole("form")).toBeNull();
    expect(screen.getByRole("status")).toBeTruthy();
    fireEvent.click(github);
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith(
        "https://github.com/login/oauth/authorize?state=opaque",
      ),
    );
    expect(mocks.password).not.toHaveBeenCalled();
    expect(mocks.send).not.toHaveBeenCalled();
  });

  it("uses the submit busy state and aborts an in-flight login when leaving the page", async () => {
    let finishLogin!: (value: object) => void;
    mocks.password.mockReturnValueOnce(
      new Promise((resolve) => {
        finishLogin = resolve;
      }),
    );
    const view = render(<LoginForm returnTo="/topics" />);
    await screen.findByLabelText("邮箱或用户名");
    fireEvent.submit(screen.getByRole("form", { name: "账号密码登录" }));
    await waitFor(() => expect(mocks.password).toHaveBeenCalledTimes(1));
    const signal = mocks.password.mock.calls[0][1].signal as AbortSignal;
    expect(screen.getByRole("button", { name: "正在登录…" })).toHaveProperty(
      "disabled",
      true,
    );
    expect(
      screen.getByRole("button", { name: "使用邮箱验证码登录" }),
    ).toHaveProperty("disabled", true);
    expect(screen.queryByRole("button", { name: "取消" })).toBeNull();
    fireEvent.submit(screen.getByRole("form", { name: "账号密码登录" }));
    expect(mocks.password).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => finishLogin({}));
    expect(mocks.toastInfo).not.toHaveBeenCalled();
    expect(mocks.toastError).not.toHaveBeenCalled();
    expect(mocks.replace).not.toHaveBeenCalled();
    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it("keeps code sending on the primary button without an extra cancellation action", async () => {
    let finishSend!: (value: HotKeyAPI.EmailChallengeView) => void;
    mocks.send.mockReturnValueOnce(
      new Promise((resolve) => {
        finishSend = resolve;
      }),
    );
    render(<LoginForm returnTo="/topics" />);
    await selectEmail();
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "reader@example.com" },
    });
    fireEvent.submit(screen.getByRole("form", { name: "邮箱验证码登录" }));
    expect(screen.getByRole("button", { name: "正在发送…" })).toHaveProperty(
      "disabled",
      true,
    );
    expect(screen.getByLabelText("邮箱")).toHaveProperty("disabled", true);
    expect(screen.queryByRole("button", { name: "取消" })).toBeNull();
    fireEvent.submit(screen.getByRole("form", { name: "邮箱验证码登录" }));
    expect(mocks.send).toHaveBeenCalledTimes(1);
    await act(async () =>
      finishSend({
        challenge_id: "00000000-0000-4000-8000-000000000001",
        expires_at: "2100-01-01T00:00:00Z",
        resend_after_seconds: 60,
      }),
    );
    expect(screen.getByRole("button", { name: "验证并继续" })).toHaveProperty(
      "disabled",
      false,
    );
    expect(screen.getByLabelText("验证码")).toBeTruthy();
  });

  it("retries login options after a network failure", async () => {
    let finishOptions!: (value: HotKeyAPI.LoginOptionsView) => void;
    mocks.options
      .mockRejectedValueOnce(
        new ApiRequestError({ kind: "network", message: "offline" }),
      )
      .mockReturnValueOnce(
        new Promise((resolve) => {
          finishOptions = resolve;
        }),
      );
    render(<LoginForm returnTo="/topics" />);
    await waitFor(() => expect(mocks.toastError).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
    const heading = screen.getByRole("heading", { name: "登录" });
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
    expect(
      screen.getByRole("status", { name: "正在读取登录方式" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "重新读取" })).toBeNull();
    await act(async () =>
      finishOptions({ password: true, email: true, github: true }),
    );
    await screen.findByLabelText("邮箱或用户名");
    expect(screen.getByRole("heading", { name: "登录" })).toBe(heading);
    expect(mocks.options).toHaveBeenCalledTimes(2);
  });
});
