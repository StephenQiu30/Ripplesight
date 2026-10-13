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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

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

it("restores the menu trigger after its login item has unmounted", async () => {
  render(
    <IdentitySessionProvider session={null}>
      <LoginProvider>
        <DropdownMenu>
          <DropdownMenuTrigger>更多导航</DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem asChild>
              <AuthLink href="/monitors/new">设置关键词</AuthLink>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </LoginProvider>
    </IdentitySessionProvider>,
  );
  const trigger = screen.getByRole("button", { name: "更多导航" });
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
  const item = await screen.findByRole("menuitem", { name: "设置关键词" });
  item.focus();
  fireEvent.click(item);
  await screen.findByRole("dialog", { name: "登录 Ripplesight" });
  await waitFor(() => expect(screen.queryByRole("menuitem")).toBeNull());
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(document.activeElement).toBe(trigger);
  expect(mocks.replace).not.toHaveBeenCalled();
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

it.each([
  [true, false, false],
  [false, true, false],
  [false, false, true],
  [true, true, false],
  [true, false, true],
  [false, true, true],
  [true, true, true],
  [false, false, false],
])(
  "keeps one initially focused close control for options %s/%s/%s",
  async (password, email, github) => {
    mocks.options.mockResolvedValue({ password, email, github });
    render(<Reader />);
    const trigger = screen.getByRole("link", { name: "设置关键词" });
    trigger.focus();
    fireEvent.click(trigger);
    await screen.findByRole("toolbar", { name: "登录方式" });
    const close = screen.getByRole("button", { name: "关闭" });
    await waitFor(() => expect(document.activeElement).toBe(close));
    expect(screen.getAllByRole("button", { name: "关闭" })).toHaveLength(1);
    fireEvent.click(close);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
    expect(mocks.password).not.toHaveBeenCalled();
    expect(mocks.replace).not.toHaveBeenCalled();
  },
);

it("can close while options are pending without a late response reopening login", async () => {
  let resolveOptions!: (options: {
    password: boolean;
    email: boolean;
    github: boolean;
  }) => void;
  mocks.options.mockReturnValue(
    new Promise((resolve) => {
      resolveOptions = resolve;
    }),
  );
  render(<Reader />);
  fireEvent.change(screen.getByLabelText("阅读筛选"), {
    target: { value: "保留筛选" },
  });
  const trigger = screen.getByRole("link", { name: "设置关键词" });
  trigger.focus();
  fireEvent.click(trigger);
  await screen.findByRole("status", { name: "正在读取登录方式" });
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await act(async () => {
    resolveOptions({ password: true, email: true, github: true });
  });
  await waitFor(() => expect(document.activeElement).toBe(trigger));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect((screen.getByLabelText("阅读筛选") as HTMLInputElement).value).toBe(
    "保留筛选",
  );
  expect(mocks.password).not.toHaveBeenCalled();
});

it("can continue reading after the login options fail", async () => {
  mocks.options.mockRejectedValue(new Error("unavailable"));
  render(<Reader />);
  const trigger = screen.getByRole("link", { name: "平台接入" });
  trigger.focus();
  fireEvent.click(trigger);
  await screen.findByText("登录方式暂时不可用");
  fireEvent.click(screen.getByRole("button", { name: "暂不登录，继续浏览" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(document.activeElement).toBe(trigger);
  expect(mocks.password).not.toHaveBeenCalled();
  expect(mocks.replace).not.toHaveBeenCalled();
});
