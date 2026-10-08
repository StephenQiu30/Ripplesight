// @vitest-environment happy-dom
import { expectOnePageHeading } from "../../page-heading";
import { type ReactElement } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiRequestError } from "@/request";
import { publicItem } from "../components/home-fixtures";

const api = vi.hoisted(() => ({
  items: vi.fn(),
  timeline: vi.fn(),
  topics: vi.fn(),
  connection: vi.fn(),
  site: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("next/server", () => ({ connection: api.connection }));
vi.mock("@/api/gongkaifabu", () => ({
  listPublicItems: api.items,
  getPublicReadingTimeline: api.timeline,
  getPublicTopicDirectory: api.topics,
}));
vi.mock("@/api/zhandiziliao", () => ({ getPublicSiteMeta: api.site }));
import DiscoverPage, { generateMetadata } from "@/app/discover/page";
import StarredPage, {
  metadata as starredMetadata,
} from "@/app/discover/starred/page";

beforeEach(() => {
  vi.resetAllMocks();
  api.site.mockResolvedValue({
    public_base_url: "https://hotkey.test",
    robots_index: true,
  });
  api.items.mockResolvedValue({
    items: [publicItem],
    next_cursor: "signed-next",
    snapshot_at: "2026-10-06T08:00:00Z",
    source_status: [],
  });
  api.topics.mockResolvedValue({
    topics: [
      {
        slug: "research",
        name: "研究专题",
        definition: "测试专题定义",
        group: "field",
        total: 4,
        recent: 2,
        latest_at: null,
        indexable: false,
      },
    ],
    refresh_at: null,
  });
});
afterEach(() => {
  if (document.body.textContent) expectOnePageHeading();
  cleanup();
  localStorage.clear();
});

async function read(params: Record<string, string> = {}) {
  const shell = await DiscoverPage({ searchParams: Promise.resolve(params) });
  const boundary = shell.props.children as ReactElement<{
    params: Record<string, string>;
  }>;
  const resolve = boundary.type as (
    props: typeof boundary.props,
  ) => Promise<ReactElement>;
  return { shell, content: await resolve(boundary.props) };
}

it("keeps discovery anonymous, preserves every filter/cursor, and provides a list loading state", async () => {
  const params = {
    q: "研究",
    mode: "selected",
    window: "7d",
    category: "paper",
    by: "published",
    channel: "news",
    source_key: "rss",
    tag: "研究",
    topic: "research",
    search_order: "time",
    cursor: "current",
  };
  const { shell, content } = await read(params);
  const loading = render(shell.props.fallback);
  expect(screen.getByRole("status", { name: "正在检索公开资讯" })).toBeTruthy();
  expectOnePageHeading();
  loading.unmount();
  expect(api.items).toHaveBeenCalledWith({ ...params, limit: 40 });
  expect(api.timeline).not.toHaveBeenCalled();
  expect(api.connection).toHaveBeenCalledOnce();
  render(content);
  expect(screen.getByRole("heading", { name: "探索", level: 1 })).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "公开资讯测试条目" }).getAttribute("href"),
  ).toBe(publicItem.reading_url);
  expect(
    screen.getByRole("link", { name: "研究专题" }).getAttribute("href"),
  ).toBe("/discover/topics/research");
  const next = new URL(
    screen.getByRole("link", { name: "下一页" }).getAttribute("href")!,
    "https://hotkey.test",
  );
  expect(next.searchParams.get("cursor")).toBe("signed-next");
  expect(next.searchParams.get("q")).toBe("研究");
  expect(next.searchParams.get("source_key")).toBe("rss");
  const first = new URL(
    screen.getByRole("link", { name: "回到第一页" }).getAttribute("href")!,
    "https://hotkey.test",
  );
  expect(first.searchParams.has("cursor")).toBe(false);
  expect(first.searchParams.get("q")).toBe("研究");
});

it("retains selected timeline filters and the grouped reports/developments", async () => {
  api.timeline.mockResolvedValue({
    cards: [
      {
        key: "card-1",
        anchor_at: publicItem.timeline_at,
        item: publicItem,
        group: {
          fact_id: "fact-1",
          event_id: "event-1",
          additional_source_count: 2,
          development_count: 2,
          latest_development: { title: "新进展" },
        },
      },
    ],
    filters: {
      mode: "selected",
      window: "7d",
      channel: "news",
      category: "paper",
    },
    next_cursor: null,
    snapshot_at: "2026-10-06T08:00:00Z",
  });
  const { content } = await read({
    mode: "selected",
    window: "7d",
    category: "paper",
    channel: "news",
    tag: "研究",
    topic: "research",
    cursor: "timeline-cursor",
  });
  expect(api.items).not.toHaveBeenCalled();
  expect(api.timeline).toHaveBeenCalledWith({
    window: "7d",
    category: "paper",
    channel: "news",
    tag: "研究",
    topic: "research",
    source_key: undefined,
    cursor: "timeline-cursor",
    limit: 20,
  });
  render(content);
  expect(screen.getByText("最新进展 · 新进展")).toBeTruthy();
  expect(screen.getByRole("button", { name: /展开同事实报道/ })).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "展开 2 个事实与进展" }),
  ).toBeTruthy();
});

it("isolates a topic failure while keeping search results and exposing only code/status", async () => {
  api.topics.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      code: "publication_not_configured",
      status: 503,
      message: "private detail",
    }),
  );
  const { content } = await read({ q: "研究" });
  render(content);
  expect(screen.getByRole("link", { name: "公开资讯测试条目" })).toBeTruthy();
  expect(screen.getByText("publication_not_configured · 503")).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "重新读取专题" }).getAttribute("href"),
  ).toBe("/discover?q=%E7%A0%94%E7%A9%B6");
  expect(screen.queryByText("private detail")).toBeNull();
});

it.each(["publication_search_busy", "publication_not_configured"])(
  "keeps filters and topic entries when results fail with %s",
  async (code) => {
    api.items.mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        code,
        status: 503,
        message: "private detail",
      }),
    );
    const { content } = await read({ q: "研究", cursor: "current" });
    render(content);
    expect(screen.getByText(`${code} · 503`)).toBeTruthy();
    expect(screen.getByRole("search", { name: "公开资讯检索" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "研究专题" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "重新读取" }).getAttribute("href"),
    ).toContain("cursor=current");
    expect(screen.queryByText("private detail")).toBeNull();
  },
);

it("shows separate empty results and topic states with a next step", async () => {
  api.items.mockResolvedValue({
    items: [],
    next_cursor: null,
    snapshot_at: "2026-10-06T08:00:00Z",
  });
  api.topics.mockResolvedValue({ topics: [], refresh_at: null });
  const { content } = await read();
  render(content);
  expect(screen.getByText("没有找到资讯")).toBeTruthy();
  expect(screen.getByText("暂无公开专题")).toBeTruthy();
  expect(screen.getByRole("link", { name: "清除筛选" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "下一页" })).toBeNull();
});

it.each([403, 503])(
  "keeps simultaneous HTTP %s failures below the discovery h1",
  async (status) => {
    const error = new ApiRequestError({
      kind: "http",
      status,
      code: "public_read_failed",
      message: "failed",
    });
    api.items.mockRejectedValue(error);
    api.topics.mockRejectedValue(error);
    const { content } = await read();
    render(content);
    expect(
      screen.getAllByRole(status === 403 ? "status" : "alert"),
    ).toHaveLength(2);
    expectOnePageHeading();
    expect(
      screen.getByRole("heading", { level: 2, name: "专题暂不可读" }),
    ).toBeTruthy();
  },
);

it("preserves discovery indexing gates and the local favorites noindex metadata", async () => {
  expect(
    (await generateMetadata({ searchParams: Promise.resolve({ q: "研究" }) }))
      .robots,
  ).toMatchObject({ index: false });
  expect(api.items).not.toHaveBeenCalled();
  api.items.mockResolvedValue({ items: [{ ...publicItem, indexable: true }] });
  expect(
    (await generateMetadata({ searchParams: Promise.resolve({}) })).robots,
  ).toMatchObject({ index: true });
  expect(starredMetadata.robots).toEqual({ index: false, follow: false });
});

it("restores the favorites URL fields with safe defaults and an explicit local title", async () => {
  const page = await StarredPage({
    searchParams: Promise.resolve({
      category: "industry",
      view: "read",
      page: "2",
    }),
  });
  expect(page.props).toMatchObject({
    full: true,
    initialCategory: "industry",
    initialView: "read",
    initialPage: 2,
  });
  render(page);
  expect(screen.getByRole("heading", { level: 1, name: "收藏" })).toBeTruthy();
  cleanup();
  const invalid = await StarredPage({
    searchParams: Promise.resolve({
      category: "event",
      view: "bad",
      page: "-2",
    }),
  });
  expect(invalid.props).toMatchObject({
    initialCategory: "all",
    initialView: "saved",
    initialPage: 1,
  });
});

it("bounds the discovery sidebar while keeping full-directory navigation and count in the filter group", async () => {
  api.topics.mockResolvedValue({
    topics: Array.from({ length: 38 }, (_, i) => ({
      slug: `topic-${i}`,
      name: `专题${i}`,
      definition: "很长的专题定义".repeat(30),
      group: "field",
      total: 4,
      recent: 2,
      latest_at: null,
      indexable: false,
    })),
    refresh_at: null,
  });
  const { content } = await read();
  render(content);
  const topics = within(
    screen.getByRole("complementary", { name: "按专题浏览" }),
  );
  expect(topics.getAllByRole("listitem")).toHaveLength(6);
  expect(topics.queryByRole("link", { name: "专题6" })).toBeNull();
  expect(
    topics.getByRole("link", { name: "全部专题" }).getAttribute("href"),
  ).toBe("/discover/topics");
  expect(
    within(screen.getByRole("group", { name: "检索筛选" })).getByText(
      /本页资讯 1 条/,
    ),
  ).toBeTruthy();
});

it("keeps source failures available behind a compact, keyboard-operable disclosure", async () => {
  api.items.mockResolvedValue({
    items: [],
    next_cursor: null,
    snapshot_at: "2026-10-08T00:00:00Z",
    source_status: Array.from({ length: 11 }, (_, i) => ({
      source_key: `source-${i}`,
      name: `异常来源${i}`,
      enabled: true,
      health: "failing",
      last_success_at: null,
    })),
  });
  const { content } = await read();
  render(content);
  const trigger = screen.getByRole("button", { name: "查看 11 个来源的状态" });
  expect(trigger.getAttribute("aria-expanded")).toBe("false");
  expect(within(screen.getByRole("alert")).queryByText(/异常来源0/)).toBeNull();
  fireEvent.click(trigger);
  expect(trigger.getAttribute("aria-expanded")).toBe("true");
  expect(within(screen.getByRole("alert")).getByText(/异常来源0/)).toBeTruthy();
  expect(screen.getByRole("heading", { name: "没有找到资讯" })).toBeTruthy();
});
