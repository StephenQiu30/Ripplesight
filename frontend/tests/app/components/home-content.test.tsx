// @vitest-environment happy-dom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

vi.mock("next/image", () => ({ default: () => null }));

import { HomeContent } from "@/app/components/home-content";
import { IdentitySessionProvider } from "@/components/auth/session-context";

afterEach(cleanup);

it("keeps the welcome headline and routes the main action through login", () => {
  render(<HomeContent />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
    "关注你在意的，看见新的变化。",
  );
  expect(
    screen.getByRole("link", { name: "开始使用" }).getAttribute("href"),
  ).toBe("/login");
});

it("offers a workspace entry after a real session is provided", () => {
  const session: HotKeyAPI.IdentitySessionView = {
    user: {
      id: "00000000-0000-4000-8000-000000000002",
      username: "reader",
      email: null,
    },
    expires_at: "2100-01-01T00:00:00Z",
  };
  render(
    <IdentitySessionProvider session={session}>
      <HomeContent />
    </IdentitySessionProvider>,
  );
  expect(
    screen.getByRole("link", { name: "进入系统" }).getAttribute("href"),
  ).toBe("/topics");
});

it("keeps the example explanatory and sends creation through a safe login return target", async () => {
  render(<HomeContent />);
  const hero = screen.getByRole("region", { name: "关注关键词，了解变化" });
  fireEvent.click(within(hero).getByRole("button", { name: "看看示例" }));
  const dialog = await screen.findByRole("dialog");
  expect(
    within(dialog).getByRole("link", { name: /创建/ }).getAttribute("href"),
  ).toBe("/login?returnTo=%2Fmonitors%2Fnew");
});
