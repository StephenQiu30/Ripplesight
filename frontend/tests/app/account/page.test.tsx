// @vitest-environment happy-dom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ session: vi.fn(), connection: vi.fn() }));
vi.mock("next/server", () => ({ connection: mocks.connection }));
vi.mock("@/components/auth/layout-session", () => ({
  readLayoutSession: mocks.session,
}));
vi.mock("@/app/account/components/account-settings", () => ({
  AccountSettings: ({
    session,
    initialSetup,
    returnTo,
  }: {
    session: HotKeyAPI.IdentitySessionView;
    initialSetup: boolean;
    returnTo: string;
  }) => (
    <div
      data-testid="credentials"
      data-setup={String(initialSetup)}
      data-return-to={returnTo}
      data-has-password={String(session.user.has_password)}
    />
  ),
}));

import AccountPage from "@/app/account/page";

const session: HotKeyAPI.IdentitySessionView = {
  user: {
    id: "00000000-0000-4000-8000-000000000002",
    username: "reader",
    email: "reader@example.com",
    has_password: false,
    github_connected: false,
  },
  expires_at: "2100-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.session.mockResolvedValue(session);
});
afterEach(cleanup);

it("passes an authenticated missing-password setup and original workspace target into the form", async () => {
  render(
    await AccountPage({
      searchParams: Promise.resolve({
        setup: "1",
        returnTo: "/jobs/job-1?state=failed",
      }),
    }),
  );
  const form = screen.getByTestId("credentials");
  expect(form.dataset.setup).toBe("true");
  expect(form.dataset.returnTo).toBe("/jobs/job-1?state=failed");
  expect(mocks.connection).toHaveBeenCalledTimes(1);
});

it("sanitizes an unsafe account setup destination before rendering", async () => {
  render(
    await AccountPage({
      searchParams: Promise.resolve({
        setup: "1",
        returnTo: "//attacker.invalid",
      }),
    }),
  );
  expect(screen.getByTestId("credentials").dataset.returnTo).toBe("/topics");
});

it("keeps a password-enabled account in ordinary settings even with a stale setup link", async () => {
  mocks.session.mockResolvedValue({
    ...session,
    user: { ...session.user, has_password: true },
  });
  render(
    await AccountPage({
      searchParams: Promise.resolve({ setup: "1", returnTo: "/topics" }),
    }),
  );
  expect(screen.getByTestId("credentials").dataset.setup).toBe("false");
});

it("preserves the safe original target when setup needs a new login", async () => {
  mocks.session.mockResolvedValue(null);
  render(
    await AccountPage({
      searchParams: Promise.resolve({
        setup: "1",
        returnTo: "/content?state=unread",
      }),
    }),
  );
  const login = new URL(
    screen.getByRole("link", { name: "登录" }).getAttribute("href")!,
    "https://hotkey.test",
  );
  expect(login.searchParams.get("returnTo")).toBe("/content?state=unread");
  expect(screen.queryByTestId("credentials")).toBeNull();
});
