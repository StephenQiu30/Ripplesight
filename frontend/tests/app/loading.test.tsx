// @vitest-environment happy-dom
import { expectOnePageHeading } from "../page-heading";

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Loading from "@/app/loading";
import LoginLoading from "@/app/login/loading";
vi.mock("@/api/xitongzhuangtai", () => ({
  getReadiness: vi.fn(async () => undefined),
}));

import { BasicLayout } from "@/layout/basic-layout";
const route = vi.hoisted(() => ({ pathname: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => route.pathname }));
beforeEach(() => {
  route.pathname = "/";
});

afterEach(() => {
  if (document.body.textContent) expectOnePageHeading();
  cleanup();
});

describe("route loading", () => {
  it("announces global loading inside the existing shell", () => {
    render(
      <BasicLayout>
        <Loading />
      </BasicLayout>,
    );
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("banner", { name: "移动站点导航" })).toBeTruthy();
    expect(
      screen.getByRole("complementary", { name: "站点侧边栏" }),
    ).toBeTruthy();
    expect(screen.getByRole("contentinfo")).toBeTruthy();
    expect(
      screen
        .getByRole("status", { name: "页面加载中" })
        .getAttribute("aria-busy"),
    ).toBe("true");
  });

  it("keeps the login content visible while announcing its non-interactive placeholder", () => {
    route.pathname = "/login";
    render(
      <BasicLayout>
        <LoginLoading />
      </BasicLayout>,
    );
    expect(screen.queryByRole("banner")).toBeNull();
    expect(
      screen.getByRole("heading", { name: "登录Ripplesight" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("complementary", { name: "Ripplesight" }),
    ).toBeTruthy();
    expect(
      within(screen.getByRole("main"))
        .getAllByRole("link", { name: "使用条款" })[0]
        .getAttribute("href"),
    ).toBe("/terms");
    expect(
      screen
        .getByRole("status", { name: "正在读取登录方式" })
        .parentElement?.getAttribute("aria-busy"),
    ).toBe("true");
    const main = within(screen.getByRole("main"));
    expect(main.queryByRole("textbox")).toBeNull();
    expect(
      within(
        screen.getByRole("status", { name: "正在读取登录方式" }).parentElement!,
      ).queryByRole("button"),
    ).toBeNull();
    expect(
      within(screen.getByRole("contentinfo")).getByRole("button", {
        name: "使用指南",
      }),
    ).toBeTruthy();
  });
});
