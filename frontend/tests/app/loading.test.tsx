// @vitest-environment happy-dom
import { expectOnePageHeading } from "../page-heading";

import { cleanup, render, screen } from "@testing-library/react";
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
    expect(
      screen.getByRole("navigation", { name: "移动站点导航" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("complementary", { name: "站点侧边栏" }),
    ).toBeTruthy();
    expect(screen.queryByRole("contentinfo")).toBeNull();
    expect(
      screen
        .getByRole("status", { name: "页面加载中" })
        .getAttribute("aria-busy"),
    ).toBe("true");
  });

  it("retains public navigation while loading the login route", () => {
    route.pathname = "/login";
    render(
      <BasicLayout>
        <LoginLoading />
      </BasicLayout>,
    );
    expect(
      screen.getByRole("complementary", { name: "站点侧边栏" }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "今日热点" })).toBeTruthy();
    expect(screen.getByRole("status", { name: "首页加载中" })).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});
