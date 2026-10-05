// @vitest-environment happy-dom

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
import { HomeContent, type HomeReading } from "@/app/components/home-content";
import { IdentitySessionProvider } from "@/components/auth/session-context";

afterEach(cleanup);

it("offers public reading before account actions and keeps unpublished content honest", () => {
  render(<HomeContent />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("首页");
  expect(
    screen.getByRole("link", { name: "浏览全部资讯" }).getAttribute("href"),
  ).toBe("/discover?mode=all&window=7d");
  expect(
    within(screen.getByRole("region", { name: "本周阅读" }))
      .getByRole("link", { name: "阅读公开周报" })
      .getAttribute("href"),
  ).toBe("/reports/weekly");
  expect(
    screen.getByRole("link", { name: "定制我的关注" }).getAttribute("href"),
  ).toBe("/login?returnTo=%2Fworkspace");
  expect(screen.getAllByText("等待新的公开内容")).toHaveLength(1);
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
    within(screen.getByRole("region", { name: "值得关注的事件" }))
      .getByRole("link", { name: /已发布的事件/ })
      .getAttribute("href"),
  ).toBe("/discover/stories/story-1");
  expect(
    within(screen.getByRole("region", { name: "值得关注的事件" })).queryByText(
      "等待新的公开内容",
    ),
  ).toBeNull();
});

it("continues to personal interests through the real session", () => {
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
    screen
      .getAllByRole("link", { name: "管理个人关注" })[0]
      .getAttribute("href"),
  ).toBe("/workspace");
});

it("keeps filters on the homepage, resets cursors on changes and preserves the scope for next page", () => {
  render(
    <HomeContent
      mode="selected"
      category="paper"
      cursor="old-cursor"
      reading={{
        items: [],
        stories: [],
        topics: [],
        editions: [],
        unavailable: [],
        nextCursor: "signed/+next=",
      }}
    />,
  );
  const categories = screen.getByRole("navigation", { name: "资讯分类" });
  expect(
    within(categories).getByRole("link", { name: "模型" }).getAttribute("href"),
  ).toBe("/?mode=selected&category=ai-models");
  expect(
    within(categories).getByRole("link", { name: "全部" }).getAttribute("href"),
  ).toBe("/?mode=selected");
  expect(
    within(categories)
      .getByRole("link", { name: "论文" })
      .getAttribute("aria-current"),
  ).toBe("page");
  expect(
    screen.getByRole("link", { name: "最新发现" }).getAttribute("href"),
  ).toBe("/?category=paper");
  const next = new URL(
    screen.getByRole("link", { name: "下一页" }).getAttribute("href")!,
    "http://localhost",
  );
  expect(next.searchParams.get("mode")).toBe("selected");
  expect(next.searchParams.get("category")).toBe("paper");
  expect(next.searchParams.get("cursor")).toBe("signed/+next=");
  expect(
    screen.getByRole("link", { name: "回到最新" }).getAttribute("href"),
  ).toBe("/?mode=selected&category=paper");
});

it("reads the real post while secondary sections fail, preserving source summary and unknown time", () => {
  const item: HotKeyAPI.PublicItemView = {
    id: "post-1",
    revision: 1,
    title: "真实帖子的标题",
    original_title: null,
    summary: "来源已经提供的摘要。",
    summary_origin: "source",
    analysis_state: "not_analyzed",
    backfill: true,
    source: { key: "rss", name: "公开来源", kind: "rss", first_party: true },
    original_url: "https://example.com/post",
    reading_url: "/items/post-1",
    published_at: null,
    discovered_at: "2026-10-04T00:00:00Z",
    timeline_at: "2026-10-04T00:00:00Z",
    category: "paper",
    tags: ["研究"],
    score: null,
    selected: false,
    reason: null,
    event_id: null,
    fact_id: null,
    indexable: false,
  };
  render(
    <HomeContent
      reading={{
        items: [item],
        stories: [],
        topics: [],
        editions: [],
        unavailable: ["stories", "topics", "editions"],
      }}
    />,
  );
  const feed = screen.getByRole("region", { name: "首页" });
  expect(within(feed).getByRole("heading", { name: item.title })).toBeTruthy();
  expect(
    within(feed).getByText("来源已经提供的摘要。", { exact: false }),
  ).toBeTruthy();
  expect(within(feed).getByText(/发现于/)).toBeTruthy();
  expect(within(feed).queryByText(/发布于/)).toBeNull();
  expect(within(feed).getByText("未分析")).toBeTruthy();
  expect(within(feed).getByText("历史导入")).toBeTruthy();
  expect(
    within(feed).getByRole("link", { name: "站内阅读" }).getAttribute("href"),
  ).toBe(item.reading_url);
  expect(screen.getByText("专题暂时无法读取。")).toBeTruthy();
  expect(screen.getByText("事件暂时无法读取。")).toBeTruthy();
});
