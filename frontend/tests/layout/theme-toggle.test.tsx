// @vitest-environment happy-dom

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const route = vi.hoisted(() => ({ pathname: "/discover" }));
const notifications = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => route.pathname }));
vi.mock("sonner", () => ({
  toast: notifications,
  Toaster: () => null,
}));

vi.mock("@/api/xitongzhuangtai", () => ({
  getReadiness: vi.fn(async () => undefined),
}));

import { BasicLayout } from "@/layout/basic-layout";
import {
  exportLocalBundle,
  importLocalBundle,
} from "@/components/publication/local-state";

let media: EventTarget & { matches: boolean };

beforeEach(() => {
  route.pathname = "/discover";
  media = Object.assign(new EventTarget(), { matches: false });
  const viewport = Object.assign(new EventTarget(), { matches: false });
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) =>
      query.includes("prefers-color-scheme") ? media : viewport,
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  notifications.error.mockReset();
});

const page = <h1>资讯正文</h1>;
const trigger = () => screen.getByRole("button", { name: /切换主题/ });

async function choose(name: string) {
  fireEvent.keyDown(trigger(), { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("menuitemradio", { name }));
  await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
}

it("has one sidebar theme control and retains the existing preference across routes and remounts", async () => {
  const view = render(<BasicLayout>{page}</BasicLayout>);
  expect(
    within(screen.getByRole("complementary", { name: "站点侧边栏" })).getByRole(
      "button",
      {
        name: /切换主题/,
      },
    ),
  ).toBe(trigger());
  expect(within(screen.getByRole("main")).queryByRole("combobox")).toBeNull();
  await choose("深色");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  expect(exportLocalBundle(localStorage).theme).toBe("dark");
  route.pathname = "/leaderboard";
  view.rerender(
    <BasicLayout>
      <h1>模型榜</h1>
    </BasicLayout>,
  );
  expect(trigger().getAttribute("aria-label")).toContain("深色");
  view.unmount();
  render(
    <BasicLayout>
      <h1>模型榜</h1>
    </BasicLayout>,
  );
  await waitFor(() =>
    expect(trigger().getAttribute("aria-label")).toContain("深色"),
  );
  fireEvent.keyDown(trigger(), { key: "ArrowDown" });
  const selected = await screen.findByRole("menuitemradio", { name: "深色" });
  expect(selected.getAttribute("aria-checked")).toBe("true");
  fireEvent.keyDown(selected, { key: "Escape" });
  await waitFor(() => expect(document.activeElement).toBe(trigger()));
});

it("follows system changes only when automatic mode is selected, including on the headerless login page", async () => {
  const view = render(<BasicLayout>{page}</BasicLayout>);
  await act(async () => {
    media.matches = true;
    media.dispatchEvent(new Event("change"));
  });
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  await choose("浅色");
  await act(async () => media.dispatchEvent(new Event("change")));
  expect(document.documentElement.classList.contains("dark")).toBe(false);
  await choose("跟随系统");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  route.pathname = "/login";
  view.rerender(
    <BasicLayout>
      <h1>登录</h1>
    </BasicLayout>,
  );
  expect(screen.queryByRole("banner")).toBeNull();
  await act(async () => {
    media.matches = false;
    media.dispatchEvent(new Event("change"));
  });
  expect(document.documentElement.classList.contains("dark")).toBe(false);
});

it("updates the global theme after importing the existing bundle and receiving cross-tab changes", async () => {
  render(<BasicLayout>{page}</BasicLayout>);
  await act(async () => {
    await importLocalBundle(
      JSON.stringify({ version: 1, starred: [], read: [], theme: "dark" }),
    );
  });
  await waitFor(() =>
    expect(trigger().getAttribute("aria-label")).toContain("深色"),
  );
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  localStorage.setItem("hotkey.publication.theme.v1", "light");
  fireEvent(window, new Event("storage"));
  await waitFor(() =>
    expect(trigger().getAttribute("aria-label")).toContain("浅色"),
  );
  expect(document.documentElement.classList.contains("dark")).toBe(false);
});

it("applies a choice when storage is unavailable and keeps it through system changes", async () => {
  vi.stubGlobal("localStorage", {
    getItem() {
      throw new Error("storage disabled");
    },
    setItem() {
      throw new Error("storage disabled");
    },
  });
  render(<BasicLayout>{page}</BasicLayout>);
  await choose("深色");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  expect(notifications.error).toHaveBeenCalledWith(
    "主题已应用，但本机存储不可用，未保存偏好。",
  );
  await act(async () => media.dispatchEvent(new Event("change")));
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  expect(trigger().getAttribute("aria-label")).toContain("深色");
});
