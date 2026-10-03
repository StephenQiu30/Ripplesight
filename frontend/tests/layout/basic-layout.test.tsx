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

import { BasicLayout } from "@/layout/basic-layout";

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
});

afterEach(cleanup);

describe("BasicLayout", () => {
  it("omits the login header and restores navigation when leaving login", () => {
    route.pathname = "/login";
    const view = render(<BasicLayout>{page}</BasicLayout>);
    const main = screen.getByRole("main");
    expect(screen.queryByRole("banner")).toBeNull();
    expect(screen.queryByRole("navigation", { name: "站点导航" })).toBeNull();
    expect(screen.getByRole("contentinfo")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "跳到正文" }).getAttribute("href"),
    ).toBe("#main-content");
    main.scrollTop = 100;
    route.pathname = "/";
    view.rerender(<BasicLayout>{page}</BasicLayout>);
    expect(screen.getByRole("banner")).toBeTruthy();
    expect(screen.getByRole("main")).toBe(main);
    expect(main.scrollTop).toBe(0);
  });

  it("shows public navigation and login without exposing the workspace menu", () => {
    render(<BasicLayout>{page}</BasicLayout>);
    expect(screen.getByRole("navigation", { name: "站点导航" })).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "登录" }).getAttribute("href"),
    ).toBe("/login");
    expect(screen.queryByRole("button", { name: "全部导航" })).toBeNull();
    expect(screen.queryByRole("button", { name: "账户菜单" })).toBeNull();
  });

  it("keeps welcome navigation public after login while offering the real workspace entry", () => {
    render(<BasicLayout session={session}>{page}</BasicLayout>);
    expect(
      screen.getByRole("link", { name: "进入系统" }).getAttribute("href"),
    ).toBe("/topics");
    expect(screen.queryByRole("navigation", { name: "工作区导航" })).toBeNull();
  });

  it("provides a single accessible main between the shared header and footer", () => {
    render(<BasicLayout session={session}>{page}</BasicLayout>);

    const header = screen.getByRole("banner");
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
    ["/monitors/topic-1", "我的关注", "/topics"],
    ["/events/event-1", "事件", "/events"],
    ["/content/content-1", "相关内容", "/content"],
  ])(
    "identifies the workspace destination of nested route %s",
    (pathname, label, href) => {
      route.pathname = pathname;
      render(<BasicLayout session={session}>{page}</BasicLayout>);

      const navigation = screen.getByRole("navigation", { name: "工作区导航" });
      const current = within(navigation).getByRole("link", {
        name: label,
        current: "page",
      });
      expect(current.getAttribute("href")).toBe(href);
      expect(
        within(navigation).getAllByRole("link", { current: "page" }),
      ).toHaveLength(1);
    },
  );

  it.each([
    ["/discover/topics/topic-1", "行业主题", "内容发现"],
    ["/reports/weekly/edition-1", "公开刊物", "内容发现"],
    ["/operations/models/capability-1", "模型能力配置", "工作管理"],
    ["/codex-resets/notice-1", "Codex 公告", "帮助与信息"],
  ])(
    "groups navigation and selects the most specific route for %s",
    async (pathname, label, group) => {
      route.pathname = pathname;
      render(<BasicLayout session={session}>{page}</BasicLayout>);
      const trigger = screen.getByRole("button", { name: "全部导航" });
      fireEvent.keyDown(trigger, { key: "ArrowDown" });

      const menu = await screen.findByRole("menu", { name: "全部导航" });
      const section = within(menu).getByRole("group", { name: group });
      expect(
        within(section)
          .getByRole("menuitem", { name: label })
          .getAttribute("aria-current"),
      ).toBe("page");
      expect(menu.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
      expect(within(menu).getAllByRole("menuitem")).toHaveLength(18);

      fireEvent.keyDown(menu, { key: "Escape" });
      await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
      await waitFor(() => expect(document.activeElement).toBe(trigger));
    },
  );

  it("resets the body scroll position when a different route renders", async () => {
    route.pathname = "/events";
    const view = render(<BasicLayout session={session}>{page}</BasicLayout>);
    const main = screen.getByRole("main");
    main.scrollTop = 480;

    route.pathname = "/content/content-1";
    view.rerender(
      <BasicLayout session={session}>
        <h1>另一页面</h1>
      </BasicLayout>,
    );

    await waitFor(() => expect(main.scrollTop).toBe(0));
    expect(
      within(main).getByRole("heading", { name: "另一页面" }),
    ).toBeTruthy();
  });

  it("retains reading position for a rerender within the same route", () => {
    route.pathname = "/events/event-1";
    const view = render(<BasicLayout session={session}>{page}</BasicLayout>);
    const main = screen.getByRole("main");
    main.scrollTop = 480;

    view.rerender(
      <BasicLayout session={session}>
        <h1>更新后的正文</h1>
      </BasicLayout>,
    );

    expect(main.scrollTop).toBe(480);
  });

  it("opens the guide from the footer and restores focus on close", async () => {
    render(<BasicLayout session={session}>{page}</BasicLayout>);
    expect(
      within(screen.getByRole("banner")).queryByRole("button", {
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
    expect(screen.getByRole("banner")).toBeTruthy();
    expect(screen.getByRole("main")).toBeTruthy();
    expect(screen.getByRole("contentinfo")).toBeTruthy();
    expect(screen.getByRole("button", { name: "使用指南" })).toBeTruthy();

    route.pathname = "/events/event-1";
    view.rerender(<BasicLayout session={session}>{page}</BasicLayout>);

    expect(
      within(screen.getByRole("navigation", { name: "工作区导航" })).getByRole(
        "link",
        { name: "事件", current: "page" },
      ),
    ).toBeTruthy();
  });
});
