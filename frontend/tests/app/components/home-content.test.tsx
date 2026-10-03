// @vitest-environment happy-dom

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
import { HomeContent, type HomeReading } from "@/app/components/home-content";
import { IdentitySessionProvider } from "@/components/auth/session-context";

afterEach(cleanup);

it("offers public reading before account actions and keeps unpublished content honest", () => {
  render(<HomeContent />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
    "在这里，看见正在发生的变化。",
  );
  expect(
    screen.getByRole("link", { name: "浏览资讯" }).getAttribute("href"),
  ).toBe("/discover");
  expect(
    screen.getByRole("link", { name: "阅读公开周报" }).getAttribute("href"),
  ).toBe("/reports/weekly");
  expect(
    screen.getByRole("link", { name: "定制我的周报" }).getAttribute("href"),
  ).toBe("/login?returnTo=%2Fworkspace");
  expect(screen.getAllByText("等待新的公开内容")).toHaveLength(2);
  expect(screen.queryByText("暂时无法读取")).toBeNull();
});

it("preserves available stories when the news section cannot be read", () => {
  const reading: HomeReading = {
    items: [],
    topics: [],
    editions: [],
    unavailable: ["items"],
    stories: [
      {
        id: "story-1",
        revision: 1,
        title: "已发布的事件",
        summary: "来自真实投影的说明",
        latest_progress: null,
        phase: "active",
        first_seen_at: "2026-10-03T00:00:00Z",
        reports: [],
      },
    ],
  };
  render(<HomeContent reading={reading} />);
  expect(screen.getByText("暂时无法读取")).toBeTruthy();
  expect(
    screen.getByRole("link", { name: /已发布的事件/ }).getAttribute("href"),
  ).toBe("/discover/stories/story-1");
  expect(
    within(screen.getByRole("region", { name: "值得关注的事件" })).queryByText(
      "等待新的公开内容",
    ),
  ).toBeNull();
});

it("continues to personal reporting through the real session", () => {
  render(
    <IdentitySessionProvider
      session={{
        user: {
          id: "00000000-0000-4000-8000-000000000002",
          username: "reader",
          has_password: true,
          github_connected: false,
          email: null,
        },
        expires_at: "2100-01-01T00:00:00Z",
      }}
    >
      <HomeContent />
    </IdentitySessionProvider>,
  );
  expect(
    screen.getByRole("link", { name: "管理我的周报" }).getAttribute("href"),
  ).toBe("/workspace");
});
