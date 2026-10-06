// @vitest-environment happy-dom
import { expectOnePageHeading } from "../../page-heading";

import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const navigation = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => navigation,
}));
import { HomeContent, type HomeReading } from "@/app/components/home-content";
import { IdentitySessionProvider } from "@/components/auth/session-context";

afterEach(() => {
  expectOnePageHeading();
  cleanup();
  vi.clearAllMocks();
});

it("offers public reading before account actions and keeps unpublished content honest", () => {
  render(<HomeContent />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
    "公开资讯",
  );
  expect(
    screen.getByRole("link", { name: "浏览全部资讯" }).getAttribute("href"),
  ).toBe("/discover?mode=all&window=7d");
  expect(
    within(screen.getByRole("region", { name: "最新刊物" }))
      .getByRole("link", { name: "阅读公开周报" })
      .getAttribute("href"),
  ).toBe("/reports/weekly");
  expect(
    screen.getByRole("link", { name: "登录设置关注" }).getAttribute("href"),
  ).toBe("/login?returnTo=%2Fworkspace");
  expect(screen.getAllByText("等待新的公开内容")).toHaveLength(1);
  expect(screen.queryByText("暂时无法读取")).toBeNull();
  expect(screen.getByRole("heading", { name: "今日 AI 热点" })).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "订阅日报" }).getAttribute("href"),
  ).toBe("/feed/daily.xml");
  expect(screen.queryByText(/每小时刷新/)).toBeNull();
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
  for (const name of ["首页内容范围", "资讯分类"]) {
    const container = screen.getByRole("radiogroup", { name }).parentElement!;
    expect(container.classList.contains("overflow-x-auto")).toBe(true);
    expect(container.classList.contains("hide-scrollbar")).toBe(true);
  }
  const categories = screen.getByRole("radiogroup", { name: "资讯分类" });
  fireEvent.click(within(categories).getByRole("radio", { name: "模型" }));
  expect(navigation.push).toHaveBeenLastCalledWith(
    "/?mode=selected&category=ai-models",
  );
  fireEvent.click(within(categories).getByRole("radio", { name: "全部" }));
  expect(navigation.push).toHaveBeenLastCalledWith("/?mode=selected");
  expect(
    within(categories)
      .getByRole("radio", { name: "论文" })
      .getAttribute("aria-checked"),
  ).toBe("true");
  const latest = within(
    screen.getByRole("radiogroup", { name: "首页内容范围" }),
  ).getByRole("radio", { name: "最新发现" });
  fireEvent.click(latest);
  expect(navigation.push).toHaveBeenLastCalledWith("/?category=paper");
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
  const feed = screen.getByRole("region", { name: "公开资讯" });
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

it("searches trimmed text with Enter and ignores composition and empty queries", () => {
  render(<HomeContent />);
  const input = screen.getAllByRole("searchbox", { name: "搜索公开资讯" })[0];
  fireEvent.keyDown(input, { key: "Enter" });
  expect(navigation.push).not.toHaveBeenCalled();
  fireEvent.change(input, { target: { value: "  模型 & 产品  " } });
  fireEvent.keyDown(input, { key: "Enter", isComposing: true });
  expect(navigation.push).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: "Enter" });
  const url = new URL(navigation.push.mock.calls[0][0], "http://localhost");
  expect(url.pathname).toBe("/discover");
  expect(url.searchParams.get("q")).toBe("模型 & 产品");
  expect(url.searchParams.get("mode")).toBe("all");
  expect(url.searchParams.get("window")).toBe("7d");
});

it("keeps all four failures local, exposes safe codes, hides unavailable counts and retries the current URL", () => {
  render(
    <HomeContent
      mode="selected"
      category="paper"
      cursor="page-2"
      reading={{
        items: [],
        stories: [],
        topics: [],
        editions: [],
        unavailable: ["items", "stories", "topics", "editions"],
        failures: { topics: { code: "publication_search_busy", status: 503 } },
      }}
    />,
  );
  expect(screen.getAllByRole("alert")).toHaveLength(4);
  expect(screen.getByText("publication_search_busy · 503")).toBeTruthy();
  expect(screen.getByText("概览暂时无法读取")).toBeTruthy();
  expect(screen.queryByText("当前资讯", { exact: false })).toBeNull();
  expect(screen.queryByText("等待新的公开内容")).toBeNull();
  expect(
    screen.getByRole("link", { name: "浏览全部资讯" }).getAttribute("href"),
  ).toBe("/discover?mode=selected&window=7d&category=paper");
  fireEvent.click(
    within(screen.getByRole("region", { name: "探索专题" })).getByRole(
      "button",
      { name: "重新加载" },
    ),
  );
  expect(navigation.refresh).toHaveBeenCalledTimes(1);
  expect(navigation.push).not.toHaveBeenCalled();
});

it("renders measured story heat, independent sources and textual badges without sentiment claims", async () => {
  const { publicStory } = await import("./home-fixtures");
  render(
    <HomeContent
      reading={{
        items: [],
        topics: [],
        editions: [],
        stories: [publicStory],
        unavailable: [],
        observedAt: "2026-10-06T08:00:00Z",
      }}
    />,
  );
  const feed = within(screen.getByRole("region", { name: "全站热点事件" }));
  expect(
    feed.getByRole("link", { name: publicStory.title }).getAttribute("href"),
  ).toBe("/discover/stories/story-1");
  expect(feed.getByLabelText("热度 1250，上升").textContent).toContain("1,250");
  expect(feed.getByText("来源骤增")).toBeTruthy();
  expect(feed.getByText("持续升温")).toBeTruthy();
  expect(feed.getByText("个独立来源", { exact: false }).textContent).toContain(
    "3",
  );
  expect(feed.getByText("1小时前")).toBeTruthy();
  expect(feed.getByText("覆盖待补全")).toBeTruthy();
  expect(screen.queryByText(/负面/)).toBeNull();
  const overview = screen.getByRole("region", { name: "当前阅读概览" });
  expect(overview.textContent).toContain("当前资讯 0 条");
  expect(overview.textContent).toContain("全站热点事件 1 个");
  expect(
    screen
      .getByText("内容更新于", { exact: false })
      .querySelector("time")
      ?.getAttribute("datetime"),
  ).toBe("2026-10-06T07:00:00Z");
});

it("provides an accessible home-shaped loading state without fabricated statistics", async () => {
  const { HomeLoading } = await import("@/app/components/home-loading");
  render(<HomeLoading />);
  expect(
    screen
      .getByRole("status", { name: "首页加载中" })
      .getAttribute("aria-busy"),
  ).toBe("true");
  expect(screen.getByRole("status", { name: "正在读取首页资讯" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "登录设置关注" })).toBeNull();
  expect(screen.queryByText(/当前资讯/)).toBeNull();
});
