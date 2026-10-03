// @vitest-environment happy-dom

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { toast } from "sonner";

vi.mock("next/navigation", () => ({
  usePathname: () => "/login",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

import { BasicLayout } from "@/layout/basic-layout";

afterEach(() => {
  toast.dismiss();
  cleanup();
  document.documentElement.classList.remove("dark");
});

it("uses the app's explicit theme and follows root theme changes", async () => {
  document.documentElement.classList.add("dark");
  render(
    <BasicLayout>
      <h1>阅读页面</h1>
    </BasicLayout>,
  );
  act(() => {
    toast("主题检查", { duration: Infinity });
  });
  await screen.findByText("主题检查");
  const toaster = document.querySelector("[data-sonner-toaster]")!;
  await waitFor(() =>
    expect(toaster.getAttribute("data-sonner-theme")).toBe("dark"),
  );
  act(() => {
    document.documentElement.classList.remove("dark");
  });
  await waitFor(() =>
    expect(toaster.getAttribute("data-sonner-theme")).toBe("light"),
  );
});

it("keeps one global Sonner outside the scrolling main and lets the user close an error", async () => {
  const view = render(
    <BasicLayout>
      <h1>登录页面</h1>
    </BasicLayout>,
  );
  act(() => {
    toast.error("请求安全校验失败", { duration: Infinity });
  });
  const message = await screen.findByText("请求安全校验失败");
  const toaster = document.querySelector("[data-sonner-toaster]")!;
  expect(document.querySelectorAll("[data-sonner-toaster]")).toHaveLength(1);
  expect(toaster.getAttribute("data-y-position")).toBe("top");
  expect(toaster.getAttribute("data-x-position")).toBe("right");
  expect(screen.getByRole("main").contains(message)).toBe(false);
  view.rerender(
    <BasicLayout>
      <h1>更新后的页面</h1>
    </BasicLayout>,
  );
  expect(document.querySelectorAll("[data-sonner-toaster]")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "关闭通知" }));
  await waitFor(() =>
    expect(screen.queryByText("请求安全校验失败")).toBeNull(),
  );
});
