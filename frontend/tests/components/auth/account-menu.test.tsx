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
  logout: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/api/identity", () => ({ deleteIdentitySession: mocks.logout }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh }),
}));

import { AccountMenu } from "@/components/auth/account-menu";
import { IdentitySessionProvider } from "@/components/auth/session-context";

const session: HotKeyAPI.IdentitySessionView = {
  user: {
    id: "00000000-0000-4000-8000-000000000002",
    username: "reader",
    has_password: true,
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
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    "退出失败，请重试。",
  );
  expect(mocks.replace).not.toHaveBeenCalled();
});
