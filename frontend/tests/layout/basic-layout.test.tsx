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

vi.mock("@/api/xitongzhuangtai", () => ({ getReadiness: vi.fn() }));

import { getReadiness } from "@/api/xitongzhuangtai";
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
  vi.mocked(getReadiness).mockReset();
  vi.mocked(getReadiness).mockRejectedValue(new Error("service unavailable"));
});

afterEach(cleanup);

describe("BasicLayout", () => {
  it("shares the content scroller with readers while keeping location and mobile navigation outside it", () => {
    route.pathname = "/topics";
    function Reader() {
      const scroller = useLayoutScrollContainer();
      return (
        <button onClick={() => scroller?.current?.focus()}>定位正文</button>
      );
    }
    render(
      <BasicLayout session={session}>
        <Reader />
      </BasicLayout>,
    );
    const content = screen.getByRole("region", { name: "页面内容" });
    fireEvent.click(screen.getByRole("button", { name: "定位正文" }));
    expect(document.activeElement).toBe(content);
    expect(content.id).toBe("page-content");
    expect(
      content.contains(screen.getByRole("navigation", { name: "当前位置" })),
    ).toBe(false);
    expect(
      content.contains(screen.getByRole("navigation", { name: "手机导航" })),
    ).toBe(false);
    expect(content.contains(screen.getByRole("contentinfo"))).toBe(true);
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });

  it.each(["loading", "empty", "error", "forbidden"] as const)(
    "retains the shell and its single content boundary in the %s state",
    (state) => {
      route.pathname = "/topics";
      render(
        <BasicLayout session={session}>
          <PageState
            eyebrow="验证"
            state={state}
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
      expect(
        within(screen.getByRole("navigation", { name: "当前位置" })).getByText(
          "我的关注",
        ),
      ).toBeTruthy();
    },
  );
  it.each([
    ["ready", "服务就绪"],
    ["ok", "服务在线"],
  ] as const)("renders only the actual readiness %s", async (status, label) => {
    vi.mocked(getReadiness).mockResolvedValue({ status });
    render(<BasicLayout>{page}</BasicLayout>);
    const indicator = await screen.findByRole("status", { name: "服务状态" });
    expect(within(indicator).getByText(label)).toBeTruthy();
    expect(getReadiness).toHaveBeenCalledWith({
      signal: expect.any(AbortSignal),
    });
    expect(screen.queryByText(/采集正常|个平台|未读/)).toBeNull();
  });

  it.each([undefined, null, {}, { status: "unexpected" }])(
    "hides the entire readiness block for missing or invalid data %s",
    async (data) => {
      vi.mocked(getReadiness).mockResolvedValue(data as HotKeyAPI.HealthView);
      render(<BasicLayout>{page}</BasicLayout>);
      await waitFor(() => expect(getReadiness).toHaveBeenCalled());
      expect(screen.queryByRole("status", { name: "服务状态" })).toBeNull();
      expect(screen.getByRole("main")).toBeTruthy();
    },
  );

  it("hides readiness on request failure without changing the session", async () => {
    render(<BasicLayout session={session}>{page}</BasicLayout>);
    await waitFor(() => expect(getReadiness).toHaveBeenCalled());
    expect(screen.queryByRole("status", { name: "服务状态" })).toBeNull();
    expect(screen.getByRole("button", { name: "账户菜单" })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "工作台导航" })).toBeTruthy();
  });

  it("aborts readiness when leaving the shell", () => {
    vi.mocked(getReadiness).mockImplementation(() => new Promise(() => {}));
    const view = render(<BasicLayout>{page}</BasicLayout>);
    const signal = vi.mocked(getReadiness).mock.calls[0][0]?.signal;
    expect(signal?.aborted).toBe(false);
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("keeps every public destination and the anonymous mobile workspace login link", () => {
    render(<BasicLayout>{page}</BasicLayout>);
    const reading = screen.getByRole("navigation", { name: "站点导航" });
    expect(
      within(reading)
        .getAllByRole("link")
        .map((link) => link.getAttribute("href")),
    ).toEqual([
      "/",
      "/discover?mode=all",
      "/discover/topics",
      "/discover/starred",
      "/reports/weekly",
      "/leaderboard",
    ]);
    const mobile = screen.getByRole("navigation", { name: "手机导航" });
    expect(
      within(mobile)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["首页", "探索", "收藏", "工作台"]);
    expect(
      within(mobile)
        .getByRole("link", { name: "个人工作台" })
        .getAttribute("href"),
    ).toBe("/login?returnTo=%2Fworkspace");
    expect(
      within(mobile).getByRole("button", { name: "更多导航" }).textContent,
    ).toBe("更多");
  });

  it("adds and removes the workspace group when session changes", () => {
    const view = render(<BasicLayout>{page}</BasicLayout>);
    expect(screen.queryByRole("navigation", { name: "工作台导航" })).toBeNull();
    view.rerender(<BasicLayout session={session}>{page}</BasicLayout>);
    expect(screen.getByRole("navigation", { name: "工作台导航" })).toBeTruthy();
    view.rerender(<BasicLayout>{page}</BasicLayout>);
    expect(screen.queryByRole("navigation", { name: "工作台导航" })).toBeNull();
    expect(screen.getByRole("navigation", { name: "站点导航" })).toBeTruthy();
  });

  it("omits the login header and restores navigation when leaving login", () => {
    route.pathname = "/login";
    const view = render(<BasicLayout>{page}</BasicLayout>);
    const main = screen.getByRole("main");
    expect(screen.queryByRole("banner")).toBeNull();
    expect(screen.queryByRole("navigation", { name: "站点导航" })).toBeNull();
    expect(
      screen.queryByRole("complementary", { name: "站点侧边栏" }),
    ).toBeNull();
    expect(screen.queryByRole("navigation", { name: "手机导航" })).toBeNull();
    expect(getReadiness).not.toHaveBeenCalled();
    expect(screen.getByRole("contentinfo")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "跳到正文" }).getAttribute("href"),
    ).toBe("#page-content");
    const content = screen.getByRole("region", { name: "页面内容" });
    content.scrollTop = 100;
    route.pathname = "/";
    view.rerender(<BasicLayout>{page}</BasicLayout>);
    expect(screen.getByRole("banner", { name: "移动站点导航" })).toBeTruthy();
    expect(
      screen.getByRole("complementary", { name: "站点侧边栏" }),
    ).toBeTruthy();
    expect(screen.getByRole("main")).toBe(main);
    expect(content.scrollTop).toBe(0);
  });

  it("shows public navigation and login without exposing the workspace menu", () => {
    render(<BasicLayout>{page}</BasicLayout>);
    expect(screen.getByRole("navigation", { name: "站点导航" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "登录账户" }).getAttribute("href"),
    ).toBe("/login");
    expect(screen.queryByRole("button", { name: "全部导航" })).toBeNull();
    expect(screen.queryByRole("button", { name: "账户菜单" })).toBeNull();
    expect(screen.getByRole("navigation", { name: "站点导航" })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "工作台导航" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "工作台导航" })).toBeNull();
    expect(screen.queryByRole("link", { name: "工作台" })).toBeNull();
  });

  it("keeps welcome navigation public after login while offering the real workspace entry", () => {
    render(<BasicLayout session={session}>{page}</BasicLayout>);
    expect(
      screen.getByRole("link", { name: "工作台" }).getAttribute("href"),
    ).toBe("/workspace");
    expect(screen.getByRole("button", { name: "账户菜单" })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "工作区导航" })).toBeNull();
    expect(screen.getByRole("navigation", { name: "站点导航" })).toBeTruthy();
    expect(
      within(screen.getByRole("navigation", { name: "工作台导航" })).getByRole(
        "link",
        {
          name: "工作台",
        },
      ),
    ).toBeTruthy();
  });

  it("provides a single accessible main beside the sidebar with site information in the reading flow", () => {
    render(<BasicLayout session={session}>{page}</BasicLayout>);

    const header = screen.getByRole("complementary", { name: "站点侧边栏" });
    const main = screen.getByRole("main");
    const footer = screen.getByRole("contentinfo");
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(main.id).toBe("main-content");
    expect(main.tabIndex).toBe(-1);
    expect(
      within(main).getByRole("heading", { name: "页面正文" }),
    ).toBeTruthy();
    expect(
      header.compareDocumentPosition(main) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      main.compareDocumentPosition(footer) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      within(footer).getByRole("link", { name: /关于/ }).getAttribute("href"),
    ).toBe("/about");
    expect(
      within(footer).getByRole("link", { name: /隐私/ }).getAttribute("href"),
    ).toBe("/privacy");
    expect(
      within(footer)
        .getByRole("link", { name: /条款|许可/ })
        .getAttribute("href"),
    ).toBe("/terms");
    expect(
      within(footer).getByRole("link", { name: /联系/ }).getAttribute("href"),
    ).toBe("/contact");
  });

  it.each([
    ["/topics/topic-1", "我的关注", "/topics"],
    ["/monitors/topic-1", "我的关注", "/topics"],
    ["/alerts", "突发告警", "/alerts"],
    ["/reports", "我的报告", "/reports"],
    ["/reports/report-1", "我的报告", "/reports"],
  ])("selects the workspace sub-entry for %s", (pathname, label, href) => {
    route.pathname = pathname;
    render(<BasicLayout session={session}>{page}</BasicLayout>);
    expect(
      within(screen.getByRole("navigation", { name: "工作台导航" }))
        .getByRole("link", { name: label, current: "page" })
        .getAttribute("href"),
    ).toBe(href);
  });

  it.each([
    "/workspace",
    "/jobs/job-1",
    "/events/event-1",
    "/content/content-1",
    "/sources/source-1",
    "/operations/models",
    "/publication/manage",
    "/editorial-sources/source-1",
    "/feeds",
    "/hotlists",
    "/account",
    "/site/manage",
    "/editions",
    "/agent",
  ])("keeps private route %s under the workspace entry", (pathname) => {
    route.pathname = pathname;
    render(<BasicLayout session={session}>{page}</BasicLayout>);
    const navigation = screen.getByRole("navigation", { name: "站点导航" });
    expect(
      within(screen.getByRole("navigation", { name: "工作台导航" }))
        .getByRole("link", { name: "工作台", current: "page" })
        .getAttribute("href"),
    ).toBe("/workspace");
    expect(
      within(navigation).queryByRole("link", { name: "来源设置" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "全部导航" })).toBeNull();
  });

  it.each([
    ["/items/item-1", "探索"],
    ["/reports/daily/2026-10-06", "日周月刊"],
    ["/reports/weekly", "日周月刊"],
    ["/reports/monthly", "日周月刊"],
    ["/discover/starred", "本机收藏"],
    ["/leaderboard", "模型榜"],
  ])(
    "keeps the public route %s selected ahead of a broader workspace match",
    (pathname, label) => {
      route.pathname = pathname;
      render(<BasicLayout session={session}>{page}</BasicLayout>);
      expect(
        within(screen.getByRole("navigation", { name: "站点导航" })).getByRole(
          "link",
          { name: label, current: "page" },
        ),
      ).toBeTruthy();
      expect(
        within(
          screen.getByRole("navigation", { name: "工作台导航" }),
        ).queryByRole("link", { current: "page" }),
      ).toBeNull();
    },
  );

  it("selects the specific public topic route and restores mobile menu focus", async () => {
    route.pathname = "/discover/topics/topic-1";
    render(<BasicLayout session={session}>{page}</BasicLayout>);
    expect(
      within(screen.getByRole("navigation", { name: "站点导航" })).getByRole(
        "link",
        { name: "专题", current: "page" },
      ),
    ).toBeTruthy();
    const trigger = within(
      screen.getByRole("navigation", { name: "手机导航" }),
    ).getByRole("button", { name: "更多导航" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const menu = await screen.findByRole("menu", { name: "更多导航" });
    expect(
      within(menu).getByRole("menuitem", { name: "专题" }).getAttribute("href"),
    ).toBe("/discover/topics");
    expect(
      within(menu).getByRole("menuitem", { name: "账户设置" }),
    ).toBeTruthy();
    fireEvent.keyDown(menu, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("resets the body scroll position when a different route renders", async () => {
    route.pathname = "/events";
    const view = render(<BasicLayout session={session}>{page}</BasicLayout>);
    const content = screen.getByRole("region", { name: "页面内容" });
    content.scrollTop = 480;

    route.pathname = "/content/content-1";
    view.rerender(
      <BasicLayout session={session}>
        <h1>另一页面</h1>
      </BasicLayout>,
    );

    await waitFor(() => expect(content.scrollTop).toBe(0));
    expect(
      within(content).getByRole("heading", { name: "另一页面" }),
    ).toBeTruthy();
  });

  it("retains reading position for a rerender within the same route", () => {
    route.pathname = "/events/event-1";
    const view = render(<BasicLayout session={session}>{page}</BasicLayout>);
    const content = screen.getByRole("region", { name: "页面内容" });
    content.scrollTop = 480;

    view.rerender(
      <BasicLayout session={session}>
        <h1>更新后的正文</h1>
      </BasicLayout>,
    );

    expect(content.scrollTop).toBe(480);
  });

  it("opens the guide from the footer and restores focus on close", async () => {
    render(<BasicLayout session={session}>{page}</BasicLayout>);
    expect(
      within(
        screen.getByRole("complementary", { name: "站点侧边栏" }),
      ).queryByRole("button", {
        name: "使用指南",
      }),
    ).toBeNull();
    const trigger = within(screen.getByRole("contentinfo")).getByRole(
      "button",
      {
        name: "使用指南",
      },
    );
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { level: 2 })).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "关闭" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("keeps the shell usable while the router pathname is unavailable and recovers its active navigation", () => {
    route.pathname = null;
    const view = render(<BasicLayout session={session}>{page}</BasicLayout>);
    expect(screen.getByRole("banner", { name: "移动站点导航" })).toBeTruthy();
    expect(
      screen.getByRole("complementary", { name: "站点侧边栏" }),
    ).toBeTruthy();
    expect(screen.getByRole("main")).toBeTruthy();
    expect(screen.getByRole("contentinfo")).toBeTruthy();
    expect(screen.getByRole("button", { name: "使用指南" })).toBeTruthy();

    route.pathname = "/events/event-1";
    view.rerender(<BasicLayout session={session}>{page}</BasicLayout>);

    expect(
      within(screen.getByRole("navigation", { name: "工作台导航" })).getByRole(
        "link",
        { name: "工作台", current: "page" },
      ),
    ).toBeTruthy();
  });
});
