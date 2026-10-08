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
  it.each([
    ["ready", "服务就绪"],
    ["ok", "服务在线"],
  ] as const)("uses the actual readiness %s", async (status, label) => {
    vi.mocked(getReadiness).mockResolvedValue({ status });
    render(<BasicLayout>{page}</BasicLayout>);
    expect(
      within(await screen.findByRole("status", { name: "服务状态" })).getByText(
        label,
      ),
    ).toBeTruthy();
    expect(getReadiness).toHaveBeenCalledWith({
      signal: expect.any(AbortSignal),
    });
    expect(screen.queryByText(/采集正常|未读/)).toBeNull();
  });
  it.each([undefined, null, {}, { status: "unexpected" }])(
    "hides unavailable readiness without changing identity: %s",
    async (data) => {
      vi.mocked(getReadiness).mockResolvedValue(data as HotKeyAPI.HealthView);
      render(<BasicLayout session={session}>{page}</BasicLayout>);
      await waitFor(() => expect(getReadiness).toHaveBeenCalled());
      expect(screen.queryByRole("status", { name: "服务状态" })).toBeNull();
      expect(sidebar().getByRole("button", { name: "账户菜单" })).toBeTruthy();
    },
  );
  it("aborts readiness when the shell unmounts", () => {
    vi.mocked(getReadiness).mockImplementation(() => new Promise(() => {}));
    const view = render(<BasicLayout>{page}</BasicLayout>);
    const signal = vi.mocked(getReadiness).mock.calls[0][0]?.signal;
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });
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
    ).toEqual(["/topics", "/alerts", "/discover/starred"]);
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
    "/sources/source",
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
  it("omits product navigation on login and restores it on exit", () => {
    route.pathname = "/login";
    const view = render(<BasicLayout>{page}</BasicLayout>);
    expect(
      screen.queryByRole("complementary", { name: "站点侧边栏" }),
    ).toBeNull();
    expect(screen.queryByRole("navigation", { name: "手机导航" })).toBeNull();
    expect(getReadiness).not.toHaveBeenCalled();
    expect(screen.getByRole("contentinfo")).toBeTruthy();
    route.pathname = "/";
    view.rerender(<BasicLayout>{page}</BasicLayout>);
    expect(sidebar().getByRole("link", { name: "今日热点" })).toBeTruthy();
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
  it("uses the four design footer links on login", () => {
    route.pathname = "/login";
    render(<BasicLayout>{page}</BasicLayout>);
    const footer = within(screen.getByRole("contentinfo"));
    expect(
      footer.getAllByRole("link").map((link) => link.getAttribute("href")),
    ).toEqual(["/about", "/privacy", "/terms", "/changelog"]);
    expect(footer.queryByText("使用指南")).toBeNull();
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
