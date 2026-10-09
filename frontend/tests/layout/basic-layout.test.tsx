// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const route = vi.hoisted(() => ({ pathname: "/" as string | null }));
vi.mock("next/navigation", () => ({
  usePathname: () => route.pathname,
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));
import { BasicLayout, useLayoutScrollContainer } from "@/layout/basic-layout";
import { PageState } from "@/components/system/page-state";
const page = <h1>页面正文</h1>;
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
  route.pathname = "/";
  localStorage.removeItem("ripplesight-sidebar");
});
afterEach(cleanup);
const sidebar = () =>
  within(screen.getByRole("complementary", { name: "站点侧边栏" }));
async function openMore() {
  const trigger = sidebar().getByRole("button", { name: "更多导航" });
  fireEvent.keyDown(trigger, { key: "ArrowDown" });
  return {
    trigger,
    menu: await screen.findByRole("menu", { name: "更多导航" }),
  };
}

describe("Figma reading shell", () => {
  it("keeps one focusable content scroller and puts navigation outside the reading flow", () => {
    function Reader() {
      const scroller = useLayoutScrollContainer();
      return (
        <button onClick={() => scroller?.current?.focus()}>定位正文</button>
      );
    }
    render(
      <BasicLayout>
        <Reader />
      </BasicLayout>,
    );
    const content = screen.getByRole("region", { name: "页面内容" });
    fireEvent.click(screen.getByRole("button", { name: "定位正文" }));
    expect(document.activeElement).toBe(content);
    expect(content.id).toBe("page-content");
    expect(content.tabIndex).toBe(0);
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(
      content.contains(screen.getByRole("navigation", { name: "手机导航" })),
    ).toBe(false);
    expect(screen.queryByRole("navigation", { name: "当前位置" })).toBeNull();
    expect(screen.queryByRole("contentinfo")).toBeNull();
    expect(
      screen.getByRole("link", { name: "跳到正文" }).getAttribute("href"),
    ).toBe("#page-content");
  });
  it.each(["loading", "empty", "error", "forbidden"] as const)(
    "retains navigation and content boundary in the %s state",
    (state) => {
      render(
        <BasicLayout>
          <PageState
            state={state}
            eyebrow="验证"
            title="页面状态"
            description="状态说明"
          />
        </BasicLayout>,
      );
      expect(screen.getAllByRole("region", { name: "页面内容" })).toHaveLength(
        1,
      );
      expect(
        within(screen.getByRole("region", { name: "页面内容" })).getByText(
          /状态说明/,
        ),
      ).toBeTruthy();
      expect(sidebar().getByRole("link", { name: "今日热点" })).toBeTruthy();
    },
  );
  it("offers design navigation to guests while keeping private routes protected by the existing entry points", () => {
    render(<BasicLayout>{page}</BasicLayout>);
    expect(
      within(screen.getByRole("navigation", { name: "站点导航" }))
        .getAllByRole("link")
        .map((link) => link.getAttribute("href")),
    ).toEqual([
      "/",
      "/discover?mode=all",
      "/discover/stories",
      "/leaderboard",
      "/reports/daily",
    ]);
    expect(
      within(screen.getByRole("navigation", { name: "工作台导航" }))
        .getAllByRole("link")
        .map((link) => link.getAttribute("href")),
    ).toEqual([
      "/monitors/new",
      "/sources",
      "/topics",
      "/alerts",
      "/discover/starred",
    ]);
    const mobile = within(screen.getByRole("navigation", { name: "手机导航" }));
    expect(mobile.getAllByRole("link").map((link) => link.textContent)).toEqual(
      ["首页", "探索", "收藏", "监控"],
    );
    expect(
      mobile.getByRole("link", { name: "监控主题" }).getAttribute("href"),
    ).toBe("/topics");
    expect(sidebar().getByRole("link", { name: "登录账户" })).toBeTruthy();
  });
  it("updates account controls from the real session", () => {
    const view = render(<BasicLayout>{page}</BasicLayout>);
    expect(sidebar().queryByRole("button", { name: "账户菜单" })).toBeNull();
    view.rerender(<BasicLayout session={session}>{page}</BasicLayout>);
    expect(sidebar().getByRole("button", { name: "账户菜单" })).toBeTruthy();
    expect(
      within(screen.getByRole("navigation", { name: "手机导航" }))
        .getByRole("link", { name: "监控主题" })
        .getAttribute("href"),
    ).toBe("/topics");
  });
  it.each([
    ["/", "今日热点"],
    ["/items/post", "探索"],
    ["/discover/stories/story", "事件"],
    ["/events/event", "事件"],
    ["/reports/daily/2026-10-06", "日报"],
    ["/reports/weekly", "日报"],
    ["/reports/monthly", "日报"],
    ["/leaderboard", "榜单"],
    ["/topics/topic", "监控主题"],
    ["/monitors/topic", "监控主题"],
    ["/alerts", "告警"],
    ["/discover/starred", "收藏"],
  ])("selects the specific navigation for %s", (pathname, label) => {
    route.pathname = pathname;
    render(<BasicLayout session={session}>{page}</BasicLayout>);
    expect(
      sidebar().getByRole("link", { name: label, current: "page" }),
    ).toBeTruthy();
  });
  it.each([
    "/workspace",
    "/jobs/job",
    "/content/content",
    "/operations/models",
    "/publication/manage",
    "/editorial-sources/source",
    "/feeds",
    "/hotlists",
    "/account",
    "/site/manage",
    "/agent",
  ])("keeps management route %s accessible in More", async (pathname) => {
    route.pathname = pathname;
    render(<BasicLayout session={session}>{page}</BasicLayout>);
    const { menu } = await openMore();
    expect(
      within(menu)
        .getByRole("menuitem", { name: "工作台" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });
  it("retains topic navigation, theme settings, and keyboard focus in More", async () => {
    route.pathname = "/discover/topics/topic";
    render(<BasicLayout>{page}</BasicLayout>);
    const { trigger, menu } = await openMore();
    expect(
      within(menu)
        .getByRole("menuitem", { name: "专题" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(
      within(menu).getByRole("menuitemradio", { name: "深色" }),
    ).toBeTruthy();
    fireEvent.keyDown(menu, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
  it("retains public navigation behind the login route dialog", () => {
    route.pathname = "/login";
    render(<BasicLayout>{page}</BasicLayout>);
    expect(sidebar().getByRole("link", { name: "今日热点" })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "手机导航" })).toBeTruthy();
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.queryByRole("contentinfo")).toBeNull();
  });
  it("resets reading scroll on route change and preserves it within a route", () => {
    const view = render(<BasicLayout>{page}</BasicLayout>);
    const content = screen.getByRole("region", { name: "页面内容" });
    content.scrollTop = 480;
    view.rerender(
      <BasicLayout>
        <h1>更新</h1>
      </BasicLayout>,
    );
    expect(content.scrollTop).toBe(480);
    route.pathname = "/topics";
    view.rerender(
      <BasicLayout>
        <h1>主题</h1>
      </BasicLayout>,
    );
    expect(content.scrollTop).toBe(0);
  });
  it("collapses from the named trigger without remounting the page or losing reading position", async () => {
    const mounted = vi.fn();
    function Draft() {
      mounted();
      return <input aria-label="页面草稿" defaultValue="" />;
    }
    render(
      <BasicLayout>
        <Draft />
      </BasicLayout>,
    );
    const draft = screen.getByRole("textbox", { name: "页面草稿" });
    fireEvent.change(draft, { target: { value: "保留正在输入的内容" } });
    const content = screen.getByRole("region", { name: "页面内容" });
    content.scrollTop = 480;
    const beforeToggle = mounted.mock.calls.length;
    fireEvent.click(sidebar().getByRole("button", { name: "折叠侧边栏" }));
    expect(
      sidebar()
        .getByRole("button", { name: "展开侧边栏" })
        .getAttribute("aria-expanded"),
    ).toBe("false");
    expect(sidebar().getByRole("link", { name: "登录账户" })).toBeTruthy();
    expect(mounted).toHaveBeenCalledTimes(beforeToggle);
    expect(screen.getByRole("textbox", { name: "页面草稿" })).toBe(draft);
    expect((draft as HTMLInputElement).value).toBe("保留正在输入的内容");
    expect(content.scrollTop).toBe(480);
    await waitFor(() =>
      expect(
        JSON.parse(localStorage.getItem("ripplesight-sidebar")!).open,
      ).toBe(false),
    );
    fireEvent.click(sidebar().getByRole("button", { name: "展开侧边栏" }));
    expect(sidebar().getByRole("button", { name: "折叠侧边栏" })).toBeTruthy();
  });
  it("restores collapse preference and safely ignores damaged preference storage", () => {
    localStorage.setItem(
      "ripplesight-sidebar",
      JSON.stringify({ width: 280, open: false }),
    );
    const view = render(<BasicLayout>{page}</BasicLayout>);
    expect(sidebar().getByRole("button", { name: "展开侧边栏" })).toBeTruthy();
    view.unmount();
    localStorage.setItem("ripplesight-sidebar", "invalid");
    render(<BasicLayout>{page}</BasicLayout>);
    expect(sidebar().getByRole("button", { name: "折叠侧边栏" })).toBeTruthy();
  });
  it("does not intercept editor shortcuts or already handled keyboard events", () => {
    render(
      <BasicLayout>
        <input aria-label="编辑内容" />
      </BasicLayout>,
    );
    const editor = screen.getByRole("textbox", { name: "编辑内容" });
    fireEvent.keyDown(editor, { key: "b", ctrlKey: true });
    expect(sidebar().getByRole("button", { name: "折叠侧边栏" })).toBeTruthy();
    fireEvent.keyDown(window, { key: "b", ctrlKey: true });
    expect(sidebar().getByRole("button", { name: "展开侧边栏" })).toBeTruthy();
  });
  it("exposes platform configuration as a primary destination", () => {
    route.pathname = "/sources";
    render(<BasicLayout>{page}</BasicLayout>);
    expect(
      sidebar()
        .getByRole("link", { name: "平台接入", current: "page" })
        .getAttribute("href"),
    ).toBe("/sources");
  });
  it("recovers active navigation when router pathname becomes available", () => {
    route.pathname = null;
    const view = render(<BasicLayout>{page}</BasicLayout>);
    expect(
      sidebar().getByRole("link", { name: "今日热点", current: "page" }),
    ).toBeTruthy();
    route.pathname = "/discover/stories/story";
    view.rerender(<BasicLayout>{page}</BasicLayout>);
    expect(
      sidebar().getByRole("link", { name: "事件", current: "page" }),
    ).toBeTruthy();
  });
});
