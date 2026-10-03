// @vitest-environment happy-dom

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Loading from "@/app/loading";
import LoginLoading from "@/app/login/loading";
import { BasicLayout } from "@/layout/basic-layout";
const route = vi.hoisted(() => ({ pathname: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => route.pathname }));
beforeEach(() => {
  route.pathname = "/";
});

afterEach(cleanup);

describe("route loading", () => {
  it("announces global loading inside the existing shell", () => {
    render(
      <BasicLayout>
        <Loading />
      </BasicLayout>,
    );
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("banner")).toBeTruthy();
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
    expect(screen.getByRole("heading", { name: "登录知微见澜" })).toBeTruthy();
    expect(
      screen.getByRole("complementary", { name: "知微见澜" }),
    ).toBeTruthy();
    expect(
      within(screen.getByRole("main"))
        .getByRole("link", { name: "使用条款" })
        .getAttribute("href"),
    ).toBe("/terms");
    expect(
      screen
        .getByRole("status", { name: "正在读取登录方式" })
        .parentElement?.getAttribute("aria-busy"),
    ).toBe("true");
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
