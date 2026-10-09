// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useState } from "react";

const mocks = vi.hoisted(() => ({
  options: vi.fn(),
  password: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));
vi.mock("@/api/identity", () => ({
  getLoginOptions: mocks.options,
  createIdentitySession: mocks.password,
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), dismiss: vi.fn() } }));
vi.mock("next/dynamic", () => ({ default: () => LoginForm }));

import { LoginForm } from "@/app/login/components/login-form";
import { LoginProvider } from "@/components/auth/login-context";
import { AuthLink } from "@/components/auth/auth-link";
import { IdentitySessionProvider } from "@/components/auth/session-context";

function Reader() {
  const [draft, setDraft] = useState("");
  return (
    <IdentitySessionProvider session={null}>
      <LoginProvider>
        <label>
          阅读筛选
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
        <AuthLink href="/monitors/new?q=DeepSeek">设置关键词</AuthLink>
        <AuthLink href="/sources">平台接入</AuthLink>
        <AuthLink href="/login">登录账户</AuthLink>
        <AuthLink href="/discover?mode=all">继续阅读</AuthLink>
      </LoginProvider>
    </IdentitySessionProvider>
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.options.mockResolvedValue({
    password: true,
    email: false,
    github: false,
  });
  mocks.password.mockResolvedValue({});
});
afterEach(cleanup);

it("opens login over the reading page and restores its draft and focus on close", async () => {
  render(<Reader />);
  fireEvent.change(screen.getByLabelText("阅读筛选"), {
    target: { value: "研究" },
  });
  const trigger = screen.getByRole("link", { name: "设置关键词" });
  trigger.focus();
  fireEvent.click(trigger);
  await screen.findByRole("dialog", { name: "登录 Ripplesight" });
  await screen.findByLabelText("邮箱或用户名");
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect((screen.getByLabelText("阅读筛选") as HTMLInputElement).value).toBe(
    "研究",
  );
  expect(document.activeElement).toBe(trigger);
  expect(mocks.replace).not.toHaveBeenCalled();
});

it("continues the requested keyword configuration after successful login", async () => {
  render(<Reader />);
  fireEvent.click(screen.getByRole("link", { name: "设置关键词" }));
  fireEvent.change(await screen.findByLabelText("邮箱或用户名"), {
    target: { value: "reader" },
  });
  fireEvent.change(screen.getByLabelText("密码"), {
    target: { value: "test-password" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "账号密码登录" }));
  await waitFor(() =>
    expect(mocks.replace).toHaveBeenCalledWith("/monitors/new?q=DeepSeek"),
  );
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(mocks.refresh).toHaveBeenCalled();
});

it("keeps failed login open with input preserved", async () => {
  mocks.password.mockRejectedValue(new Error("unavailable"));
  render(<Reader />);
  fireEvent.click(screen.getByRole("link", { name: "平台接入" }));
  fireEvent.change(await screen.findByLabelText("邮箱或用户名"), {
    target: { value: "reader" },
  });
  fireEvent.change(screen.getByLabelText("密码"), {
    target: { value: "test-password" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "账号密码登录" }));
  await waitFor(() => expect(mocks.password).toHaveBeenCalled());
  expect(screen.getByRole("dialog")).toBeTruthy();
  expect(
    (screen.getByLabelText("邮箱或用户名") as HTMLInputElement).value,
  ).toBe("reader");
  expect(mocks.replace).not.toHaveBeenCalled();
});

it("preserves native modified clicks and does not prompt for public reading", () => {
  render(<Reader />);
  fireEvent.click(screen.getByRole("link", { name: "设置关键词" }), {
    ctrlKey: true,
  });
  fireEvent.click(screen.getByRole("link", { name: "继续阅读" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(mocks.options).not.toHaveBeenCalled();
});
