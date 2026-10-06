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
  toastDismiss: vi.fn(),
  options: vi.fn(),
  password: vi.fn(),
  send: vi.fn(),
  verify: vi.fn(),
  github: vi.fn(),
  logout: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { error: mocks.toastError, dismiss: mocks.toastDismiss },
}));
vi.mock("@/api/identity", () => ({
  getLoginOptions: mocks.options,
  createIdentitySession: mocks.password,
  sendEmailLoginCode: mocks.send,
  verifyEmailLoginCode: mocks.verify,
  startGithubLogin: mocks.github,
  deleteIdentitySession: mocks.logout,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));

import { LoginForm } from "@/app/login/components/login-form";
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

beforeEach(() => {
  vi.resetAllMocks();
  mocks.options.mockResolvedValue({
    password: true,
    email: true,
    github: true,
  } satisfies HotKeyAPI.LoginOptionsView);
  mocks.password.mockResolvedValue(session);
  mocks.verify.mockResolvedValue(session);
  mocks.send.mockResolvedValue({
    challenge_id: "00000000-0000-4000-8000-000000000001",
    expires_at: "2100-01-01T00:00:00Z",
    resend_after_seconds: 60,
  } satisfies HotKeyAPI.EmailChallengeView);
  vi.spyOn(window.location, "assign").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function preparePassword() {
  render(<LoginForm returnTo="/jobs/job-1?state=failed" />);
  const username = (await screen.findByLabelText(
    "邮箱或用户名",
  )) as HTMLInputElement;
  const password = screen.getByLabelText("密码") as HTMLInputElement;
  fireEvent.change(username, { target: { value: "reader" } });
  fireEvent.change(password, { target: { value: "test-password-only" } });
  return { username, password };
}

async function prepareEmail() {
  render(<LoginForm returnTo="/jobs/job-1?state=failed" />);
  fireEvent.click(
    await screen.findByRole("button", { name: "使用邮箱验证码登录" }),
  );
  const email = screen.getByLabelText("邮箱") as HTMLInputElement;
  fireEvent.change(email, { target: { value: "reader@example.com" } });
  fireEvent.submit(screen.getByRole("form", { name: "邮箱验证码登录" }));
  const code = (await screen.findByLabelText("验证码")) as HTMLInputElement;
  await waitFor(() => expect(code.disabled).toBe(false));
  fireEvent.change(code, { target: { value: "123456" } });
  return { email, code };
}

function submit(method: "password" | "email") {
  fireEvent.submit(
    screen.getByRole("form", {
      name: method === "password" ? "账号密码登录" : "邮箱验证码登录",
    }),
  );
}

function expectNoSessionChange() {
  expect(mocks.logout).not.toHaveBeenCalled();
  expect(mocks.replace).not.toHaveBeenCalled();
  expect(mocks.refresh).not.toHaveBeenCalled();
  expect(window.location.assign).not.toHaveBeenCalled();
}

function validationFailure(fields: string[]) {
  return new ApiRequestError({
    kind: "http",
    status: 422,
    code: "validation_error",
    message: "请检查输入内容。",
    details: fields.map((field) => ({
      location: ["body", field],
      message: "字段无效。",
      type: "value_error",
    })),
  });
}

// happy-dom does not synthesize a button's native keyboard click. Replay that
// browser default with detail=0 after verifying the key events were not cancelled.
function activateWithKeyboard(button: HTMLButtonElement, key: "Enter" | " ") {
  expect(button.tagName).toBe("BUTTON");
  expect(button.type).toBe("button");
  expect(button.disabled).toBe(false);
  expect(button.tabIndex).toBe(0);
  expect(document.activeElement).toBe(button);
  expect(fireEvent.keyDown(button, { key })).toBe(true);
  expect(fireEvent.keyUp(button, { key })).toBe(true);
  fireEvent.click(button, { detail: 0 });
}

describe("LoginForm field errors", () => {
  it.each([
    ["username"],
    ["password"],
    ["username", "password"],
    ["password", "username"],
  ])(
    "marks password fields from 422 locations and focuses the first error: %j",
    async (...fields) => {
      mocks.password.mockRejectedValueOnce(validationFailure(fields));
      const inputs = await preparePassword();
      submit("password");
      await waitFor(() => expect(mocks.toastError).toHaveBeenCalledTimes(1));
      for (const field of ["username", "password"] as const) {
        expect(inputs[field].getAttribute("aria-invalid")).toBe(
          String(fields.includes(field)),
        );
        expect(inputs[field].disabled).toBe(false);
      }
      expect(document.activeElement).toBe(
        inputs[fields[0] as keyof typeof inputs],
      );
      expect(inputs.username.value).toBe("reader");
      expect(inputs.password.value).toBe("test-password-only");
      expectNoSessionChange();
    },
  );

  it.each([["email"], ["code"], ["email", "code"], ["code", "email"]])(
    "marks email fields from 422 locations and focuses the first error: %j",
    async (...fields) => {
      mocks.verify.mockRejectedValueOnce(validationFailure(fields));
      const inputs = await prepareEmail();
      submit("email");
      await waitFor(() => expect(mocks.toastError).toHaveBeenCalledTimes(1));
      for (const field of ["email", "code"] as const) {
        expect(inputs[field].getAttribute("aria-invalid")).toBe(
          String(fields.includes(field)),
        );
        expect(inputs[field].disabled).toBe(false);
      }
      expect(document.activeElement).toBe(
        inputs[fields[0] as keyof typeof inputs],
      );
      expect(inputs.email.value).toBe("reader@example.com");
      expect(inputs.code.value).toBe("123456");
      expectNoSessionChange();
    },
  );

  it("marks username and password for 401 invalid_credentials and focuses username", async () => {
    mocks.password.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 401,
        code: "invalid_credentials",
        message: "验证失败。",
      }),
    );
    const { username, password } = await preparePassword();
    submit("password");
    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledTimes(1));
    expect(username.getAttribute("aria-invalid")).toBe("true");
    expect(password.getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(username);
    expectNoSessionChange();
  });

  it("marks only code for 401 invalid_email_code and focuses code", async () => {
    mocks.verify.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 401,
        code: "invalid_email_code",
        message: "验证失败。",
      }),
    );
    const { email, code } = await prepareEmail();
    submit("email");
    await waitFor(() => expect(mocks.toastError).toHaveBeenCalledTimes(1));
    expect(email.getAttribute("aria-invalid")).toBe("false");
    expect(code.getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(code);
    expectNoSessionChange();
  });

  it.each(["password", "email"] as const)(
    "does not mark %s fields or exit the session for a different 401 code",
    async (method) => {
      const inputs =
        method === "password" ? await preparePassword() : await prepareEmail();
      const request = method === "password" ? mocks.password : mocks.verify;
      request.mockRejectedValueOnce(
        new ApiRequestError({
          kind: "http",
          status: 401,
          code: "identity_unavailable",
          message: "invalid_credentials invalid_email_code",
        }),
      );
      const focused = screen.getByRole("button", {
        name: method === "password" ? "显示密码" : "使用 GitHub 登录",
      });
      act(() => focused.focus());
      submit(method);
      await waitFor(() => expect(mocks.toastError).toHaveBeenCalledTimes(1));
      for (const input of Object.values(inputs)) {
        expect(input.getAttribute("aria-invalid")).toBe("false");
        expect(input.disabled).toBe(false);
        expect(input.value).not.toBe("");
      }
      expect(document.activeElement).toBe(focused);
      expectNoSessionChange();
    },
  );

  it.each(["password", "email"] as const)(
    "does not mark %s fields or exit the session for a non-http network failure",
    async (method) => {
      const inputs =
        method === "password" ? await preparePassword() : await prepareEmail();
      const request = method === "password" ? mocks.password : mocks.verify;
      request.mockRejectedValueOnce(
        new ApiRequestError({ kind: "network", message: "offline" }),
      );
      submit(method);
      await waitFor(() =>
        expect(mocks.toastError).toHaveBeenCalledExactlyOnceWith(
          "暂时无法连接服务，请稍后重试。",
          { id: expect.any(String) },
        ),
      );
      for (const input of Object.values(inputs)) {
        expect(input.getAttribute("aria-invalid")).toBe("false");
        expect(input.disabled).toBe(false);
        expect(input.value).not.toBe("");
      }
      expectNoSessionChange();
    },
  );

  it.each(["password", "email"] as const)(
    "clears old %s field marks as soon as a deliberate retry starts",
    async (method) => {
      const inputs =
        method === "password" ? await preparePassword() : await prepareEmail();
      const request = method === "password" ? mocks.password : mocks.verify;
      request.mockRejectedValueOnce(validationFailure(Object.keys(inputs)));
      submit(method);
      await waitFor(() => expect(mocks.toastError).toHaveBeenCalledTimes(1));
      for (const input of Object.values(inputs))
        expect(input.getAttribute("aria-invalid")).toBe("true");

      let finishRetry!: (value: HotKeyAPI.IdentitySessionView) => void;
      request.mockReturnValueOnce(
        new Promise<HotKeyAPI.IdentitySessionView>((resolve) => {
          finishRetry = resolve;
        }),
      );
      // Do not edit the inputs: the new request itself must clear the marks.
      submit(method);
      expect(request).toHaveBeenCalledTimes(2);
      for (const input of Object.values(inputs)) {
        expect(input.getAttribute("aria-invalid")).toBe("false");
        expect(input.disabled).toBe(true);
        expect(input.value).not.toBe("");
      }
      expect(
        screen
          .getByRole("button", {
            name: method === "password" ? "正在登录…" : "正在验证…",
          })
          .getAttribute("aria-busy"),
      ).toBe("true");
      expectNoSessionChange();
      await act(async () => finishRetry(session));
      expect(mocks.replace).toHaveBeenCalledExactlyOnceWith(
        "/jobs/job-1?state=failed",
      );
      expect(mocks.refresh).toHaveBeenCalledTimes(1);
      expect(mocks.logout).not.toHaveBeenCalled();
    },
  );
});

describe("LoginForm keyboard method selection", () => {
  it("moves focus with arrows and switches forms with Enter and Space without submitting", async () => {
    const { username, password } = await preparePassword();
    const passwordMethod = screen.getByRole("button", {
      name: "使用账号密码登录",
    }) as HTMLButtonElement;
    const emailMethod = screen.getByRole("button", {
      name: "使用邮箱验证码登录",
    }) as HTMLButtonElement;
    expect(passwordMethod.getAttribute("aria-pressed")).toBe("true");
    expect(emailMethod.getAttribute("aria-pressed")).toBe("false");
    act(() => passwordMethod.focus());
    fireEvent.keyDown(passwordMethod, { key: "ArrowRight" });
    await waitFor(() => expect(document.activeElement).toBe(emailMethod));
    expect(passwordMethod.getAttribute("aria-pressed")).toBe("true");
    expect(emailMethod.getAttribute("aria-pressed")).toBe("false");
    activateWithKeyboard(emailMethod, "Enter");
    const email = await screen.findByLabelText("邮箱");
    expect(document.activeElement).toBe(email);
    expect(passwordMethod.getAttribute("aria-pressed")).toBe("false");
    expect(emailMethod.getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByRole("form", { name: "账号密码登录" })).toBeNull();

    act(() => emailMethod.focus());
    fireEvent.keyDown(emailMethod, { key: "ArrowLeft" });
    await waitFor(() => expect(document.activeElement).toBe(passwordMethod));
    activateWithKeyboard(passwordMethod, " ");
    expect(document.activeElement).toBe(screen.getByLabelText("邮箱或用户名"));
    expect(passwordMethod.getAttribute("aria-pressed")).toBe("true");
    expect(emailMethod.getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByRole("form", { name: "邮箱验证码登录" })).toBeNull();
    expect(screen.getByLabelText("邮箱或用户名")).toHaveProperty(
      "value",
      username.value,
    );
    expect(screen.getByLabelText("密码")).toHaveProperty(
      "value",
      password.value,
    );
    expect(mocks.password).not.toHaveBeenCalled();
    expect(mocks.send).not.toHaveBeenCalled();
    expect(mocks.verify).not.toHaveBeenCalled();
    expect(mocks.github).not.toHaveBeenCalled();
    expectNoSessionChange();
  });
});
