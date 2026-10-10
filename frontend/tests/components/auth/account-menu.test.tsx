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
  toastError: vi.fn(),
  logout: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: mocks.toastError } }));
vi.mock("@/api/identity", () => ({ deleteIdentitySession: mocks.logout }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/account",
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));

import { AccountMenu } from "@/components/auth/account-menu";
import { IdentitySessionProvider } from "@/components/auth/session-context";

const session: HotKeyAPI.IdentitySessionView = {
  user: {
    id: "00000000-0000-4000-8000-000000000002",
    username: "reader",
    has_password: true,
    github_connected: false,
    email: null,
  },
  expires_at: "2100-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.logout.mockResolvedValue(undefined);
});
afterEach(cleanup);

it("revokes the real session before returning to the public welcome page", async () => {
  render(
    <IdentitySessionProvider session={session}>
      <AccountMenu />
    </IdentitySessionProvider>,
  );
  fireEvent.keyDown(screen.getByRole("button", { name: "账户菜单" }), {
    key: "Enter",
  });
  fireEvent.click(await screen.findByRole("menuitem", { name: "退出登录" }));
  await waitFor(() => expect(mocks.logout).toHaveBeenCalledTimes(1));
  expect(mocks.replace).toHaveBeenCalledWith("/");
  expect(mocks.refresh).toHaveBeenCalledTimes(1);
});

it("keeps the current session visible when logout fails instead of pretending it was revoked", async () => {
  mocks.logout.mockRejectedValue(new Error("offline"));
  render(
    <IdentitySessionProvider session={session}>
      <AccountMenu />
    </IdentitySessionProvider>,
  );
  fireEvent.keyDown(screen.getByRole("button", { name: "账户菜单" }), {
    key: "Enter",
  });
  fireEvent.click(await screen.findByRole("menuitem", { name: "退出登录" }));
  await waitFor(() =>
    expect(mocks.toastError).toHaveBeenCalledWith("退出失败，请重试。"),
  );
  expect(screen.queryByRole("alert")).toBeNull();
  expect(mocks.replace).not.toHaveBeenCalled();
});

it("uses a readable heading for generated usernames while keeping the complete account identity", async () => {
  const username = "user_1234567890abcdef1234567890abcdef";
  render(
    <IdentitySessionProvider
      session={{ ...session, user: { ...session.user, username } }}
    >
      <AccountMenu />
    </IdentitySessionProvider>,
  );
  const trigger = screen.getByRole("button", { name: "账户菜单" });
  expect(trigger.textContent).toContain("我的账户");
  expect(trigger.textContent).not.toContain(username);
  fireEvent.keyDown(trigger, { key: "Enter" });
  const menu = await screen.findByRole("menu", { name: "账户菜单" });
  expect(menu.textContent).toContain(username);
  expect(menu.textContent).toContain("尚未绑定邮箱");
  expect(
    screen
      .getByRole("menuitem", { name: "账户设置" })
      .getAttribute("aria-current"),
  ).toBe("page");
  fireEvent.keyDown(menu, { key: "Escape" });
  await waitFor(() => expect(document.activeElement).toBe(trigger));
});

it("shows the same account actions and real email in the compact mobile entry", async () => {
  render(
    <IdentitySessionProvider
      session={{
        ...session,
        user: { ...session.user, email: "reader@example.test" },
      }}
    >
      <AccountMenu compact />
    </IdentitySessionProvider>,
  );
  const trigger = screen.getByRole("button", { name: "账户菜单" });
  expect(trigger.textContent).toBe("");
  fireEvent.keyDown(trigger, { key: "Enter" });
  await screen.findByRole("menu", { name: "账户菜单" });
  expect(screen.getByText("reader@example.test")).toBeTruthy();
  expect(screen.getAllByRole("menuitem")).toHaveLength(5);
});

it("prevents duplicate logout requests while keeping the pending action visible", async () => {
  let finish!: () => void;
  mocks.logout.mockReturnValue(
    new Promise<void>((resolve) => {
      finish = resolve;
    }),
  );
  render(
    <IdentitySessionProvider session={session}>
      <AccountMenu />
    </IdentitySessionProvider>,
  );
  fireEvent.keyDown(screen.getByRole("button", { name: "账户菜单" }), {
    key: "Enter",
  });
  fireEvent.click(await screen.findByRole("menuitem", { name: "退出登录" }));
  const pending = await screen.findByRole("menuitem", { name: "正在退出…" });
  expect(pending.getAttribute("aria-disabled")).toBe("true");
  fireEvent.click(pending);
  expect(mocks.logout).toHaveBeenCalledTimes(1);
  finish();
  await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/"));
});
