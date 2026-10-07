// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import { Heading } from "@/components/ui/content";
import { expectOnePageHeading } from "../../page-heading";
const notifications = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications }));
import {
  SavedItems,
  SaveItem,
  MarkItemRead,
  filterLocalItems,
} from "@/components/publication/local-reading";
import {
  SAVED_KEY,
  READ_KEY,
  savedIds,
} from "@/components/publication/local-state";
import { publicItem } from "../../app/components/home-fixtures";
import { ApiRequestError } from "@/request";
const api = vi.hoisted(() => ({ read: vi.fn() }));
vi.mock("@/api/gongkaifabu", () => ({ getSitePublicationItem: api.read }));
afterEach(() => {
  if (screen.queryByRole("region", { name: "本机收藏" }))
    expectOnePageHeading();
  cleanup();
  vi.resetAllMocks();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
  window.history.replaceState(null, "", "/discover/starred");
});

function renderSavedPage(props: ComponentProps<typeof SavedItems>) {
  const view = render(
    <>
      <Heading level={1}>本机收藏</Heading>
      <SavedItems {...props} />
    </>,
  );
  expectOnePageHeading();
  return view;
}

const id = (i: number) =>
  `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`;
it("keeps unreadable saved IDs removable and clamps pagination after cross-tab removal", async () => {
  localStorage.setItem(
    SAVED_KEY,
    JSON.stringify(Array.from({ length: 21 }, (_, i) => id(i + 1))),
  );
  api.read.mockRejectedValue(new Error("withdrawn"));
  renderSavedPage({ full: true });
  await screen.findByText(`暂时不可读取 · ${id(1)}`);
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByText(`暂时不可读取 · ${id(21)}`);
  localStorage.setItem(SAVED_KEY, JSON.stringify([id(1)]));
  fireEvent(window, new Event("storage"));
  await screen.findByText(`暂时不可读取 · ${id(1)}`);
  await waitFor(() => expect(screen.getByText("第 1 / 1 页")).toBeTruthy());
  fireEvent.click(
    screen.getByRole("button", { name: `移除不可读收藏：${id(1)}` }),
  );
  await screen.findByText("还没有收藏。");
  expectOnePageHeading();
  expect(JSON.parse(localStorage.getItem(SAVED_KEY)!)).toEqual([]);
});
it("reports corrupted stored JSON, preserves the raw bytes, and offers a retry without export", async () => {
  localStorage.setItem(SAVED_KEY, "broken JSON");
  renderSavedPage({ full: true });
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith(
      expect.stringContaining("原始数据保留"),
      { id: "local-reading-storage" },
    ),
  );
  expect(screen.queryByText(/原始数据保留/)).toBeNull();
  fireEvent(window, new Event("storage"));
  await waitFor(() =>
    expect(screen.queryByText("正在读取当前公开材料…")).toBeNull(),
  );
  expect(notifications.error).toHaveBeenCalledOnce();
  expect(localStorage.getItem(SAVED_KEY)).toBe("broken JSON");
  expect(screen.getByRole("alert", { name: "本机收藏暂不可读" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "重新读取" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "导出原始数据" })).toBeNull();
  expect(api.read).not.toHaveBeenCalled();
});

function detail(
  index: number,
  category: HotKeyAPI.PublicItemView["category"] = "paper",
): HotKeyAPI.PublicItemDetailView {
  return {
    ...publicItem,
    id: id(index),
    title: `本机资讯 ${index}`,
    reading_url: `/items/${id(index)}`,
    category,
    body: null,
    reading_mode: "summary-only",
    site_fulltext: false,
    syndicate_fulltext: false,
    markdown_available: false,
    license_name: "测试许可",
    license_url: null,
  };
}

it("maps only the actual category, including uncategorized items, without inventing events", () => {
  const items = [
    detail(1),
    detail(2, "industry"),
    { ...detail(3, null), event_id: "related-story" },
  ];
  expect(filterLocalItems(items, "all")).toEqual(items);
  expect(filterLocalItems(items, "paper")).toEqual([items[0]]);
  expect(filterLocalItems(items, "uncategorized")).toEqual([items[2]]);
  expect(filterLocalItems(items, "event")).toEqual([]);
});

it("filters the current page and restores category/view/page from the URL on refresh", async () => {
  localStorage.setItem(SAVED_KEY, JSON.stringify([id(1), id(2)]));
  api.read.mockImplementation(({ content_id }: { content_id: string }) =>
    Promise.resolve(content_id === id(1) ? detail(1) : detail(2, "industry")),
  );
  const mounted = renderSavedPage({ full: true });
  await screen.findByRole("link", { name: "本机资讯 1" });
  fireEvent.click(screen.getByRole("radio", { name: "行业" }));
  expect(screen.queryByRole("link", { name: "本机资讯 1" })).toBeNull();
  expect(screen.getByRole("link", { name: "本机资讯 2" })).toBeTruthy();
  expect(new URL(window.location.href).searchParams.get("category")).toBe(
    "industry",
  );
  mounted.unmount();
  renderSavedPage({ full: true, initialCategory: "industry" });
  await screen.findByRole("link", { name: "本机资讯 2" });
  expect(screen.queryByRole("link", { name: "本机资讯 1" })).toBeNull();
  expect(api.read).toHaveBeenCalledTimes(4);
});

it("shows independent reading history, persists its URL, and does not offer removal of read marks", async () => {
  localStorage.setItem(SAVED_KEY, JSON.stringify([id(1)]));
  localStorage.setItem(READ_KEY, JSON.stringify([id(2)]));
  api.read.mockImplementation(({ content_id }: { content_id: string }) =>
    Promise.resolve(content_id === id(1) ? detail(1) : detail(2)),
  );
  renderSavedPage({ full: true });
  await screen.findByRole("link", { name: "本机资讯 1" });
  fireEvent.click(screen.getByRole("radio", { name: "阅读记录" }));
  await screen.findByRole("link", { name: "本机资讯 2" });
  expect(screen.queryByRole("link", { name: "本机资讯 1" })).toBeNull();
  expect(screen.getByText("已读")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /取消收藏/ })).toBeNull();
  expect(new URL(window.location.href).searchParams.get("view")).toBe("read");
  expect(localStorage.getItem(READ_KEY)).toBe(JSON.stringify([id(2)]));
});

it("keeps save/remove and reading marks after remount and rejects duplicate in-flight saves", async () => {
  const mounted = render(
    <>
      <SaveItem id={id(1)} />
      <MarkItemRead id={id(1)} />
    </>,
  );
  const save = screen.getByRole("button", { name: "本机收藏" });
  fireEvent.click(save);
  expect(save.getAttribute("disabled")).not.toBeNull();
  await screen.findByRole("button", { name: "取消本机收藏" });
  expect(savedIds(localStorage)).toEqual([id(1)]);
  expect(JSON.parse(localStorage.getItem(READ_KEY)!)).toEqual([id(1)]);
  mounted.unmount();
  api.read.mockResolvedValue(detail(1));
  const list = renderSavedPage({ full: true });
  await screen.findByText("已读");
  fireEvent.click(screen.getByRole("button", { name: "取消收藏：本机资讯 1" }));
  await screen.findByText("还没有收藏。");
  expectOnePageHeading();
  expect(savedIds(localStorage)).toEqual([]);
  list.unmount();
  renderSavedPage({ full: true });
  await screen.findByText("还没有收藏。");
  expectOnePageHeading();
  expect(JSON.parse(localStorage.getItem(READ_KEY)!)).toEqual([id(1)]);
});

it("handles a privacy-mode storage getter failure without API calls and recovers on retry", async () => {
  const actual = localStorage;
  vi.stubGlobal("localStorage", {
    getItem: () => {
      throw new Error("SecurityError");
    },
  });
  renderSavedPage({ full: true });
  await screen.findByRole("alert", { name: "本机收藏暂不可读" });
  expect(api.read).not.toHaveBeenCalled();
  vi.stubGlobal("localStorage", actual);
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  await screen.findByText("还没有收藏。");
  expectOnePageHeading();
  expect(screen.queryByRole("alert")).toBeNull();
});

it("does not change a saved record after a quota failure and reports the failed operation", async () => {
  const actual = localStorage;
  actual.setItem(SAVED_KEY, JSON.stringify([id(1)]));
  api.read.mockResolvedValue(detail(1));
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => actual.getItem(key),
    setItem: () => {
      throw new Error("QuotaExceededError");
    },
  });
  renderSavedPage({ full: true });
  await screen.findByRole("link", { name: "本机资讯 1" });
  fireEvent.click(screen.getByRole("button", { name: "取消收藏：本机资讯 1" }));
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith("存储不可用，未删除。"),
  );
  expect(actual.getItem(SAVED_KEY)).toBe(JSON.stringify([id(1)]));
  expect(screen.getByRole("link", { name: "本机资讯 1" })).toBeTruthy();
});

it("shows safe API error code/status beside unreadable IDs and keeps other items readable", async () => {
  localStorage.setItem(SAVED_KEY, JSON.stringify([id(1), id(2)]));
  api.read.mockImplementation(({ content_id }: { content_id: string }) =>
    content_id === id(1)
      ? Promise.resolve(detail(1))
      : Promise.reject(
          new ApiRequestError({
            kind: "http",
            code: "publication_withdrawn",
            status: 404,
            message: "private internal details",
          }),
        ),
  );
  renderSavedPage({ full: true });
  await screen.findByRole("link", { name: "本机资讯 1" });
  expectOnePageHeading();
  expect(screen.getAllByText("publication_withdrawn · 404")).toHaveLength(2);
  expect(screen.getByText(`暂时不可读取 · ${id(2)}`)).toBeTruthy();
  expect(screen.queryByText("private internal details")).toBeNull();
  expect(screen.queryByText("还没有收藏。")).toBeNull();
});

it("exports only selected readable links and keeps hidden or withdrawn materials out of the file", async () => {
  localStorage.setItem(SAVED_KEY, JSON.stringify([id(1), id(2), id(3)]));
  api.read.mockImplementation(({ content_id }: { content_id: string }) =>
    content_id === id(3)
      ? Promise.reject(new Error("withdrawn"))
      : Promise.resolve({
          ...detail(content_id === id(1) ? 1 : 2),
          body: "PRIVATE FULL TEXT MUST NOT BE EXPORTED",
        }),
  );
  const create = vi.fn<(blob: Blob) => string>().mockReturnValue("blob:review");
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL = create;
      static revokeObjectURL = vi.fn();
    },
  );
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  renderSavedPage({ full: true });
  await screen.findByRole("checkbox", { name: "选择收藏：本机资讯 1" });
  fireEvent.click(
    screen.getByRole("checkbox", { name: "选择收藏：本机资讯 1" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "导出 Markdown" }));
  const content = await (create.mock.calls[0][0] as Blob).text();
  expect(content).toContain("本机资讯 1");
  expect(content).toContain(publicItem.original_url);
  expect(content).not.toContain("本机资讯 2");
  expect(content).not.toContain(id(3));
  expect(content).not.toContain("PRIVATE FULL TEXT");
  expect(click).toHaveBeenCalledOnce();
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索本页收藏" }), {
    target: { value: "不存在的关键词" },
  });
  expect(screen.queryByRole("button", { name: "导出 Markdown" })).toBeNull();
  expect(
    screen.getByRole("button", { name: "导出本页" }).hasAttribute("disabled"),
  ).toBe(true);
});

it("clears a search with no matching saved item without deleting stored IDs", async () => {
  localStorage.setItem(SAVED_KEY, JSON.stringify([id(1)]));
  api.read.mockResolvedValue(detail(1));
  renderSavedPage({ full: true });
  await screen.findByRole("checkbox", { name: "选择收藏：本机资讯 1" });
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索本页收藏" }), {
    target: { value: "找不到" },
  });
  expect(
    screen.getByRole("heading", { name: "本页没有匹配的收藏" }),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "清除筛选" }));
  expect(
    screen.getByRole("checkbox", { name: "选择收藏：本机资讯 1" }),
  ).toBeTruthy();
  expect(savedIds(localStorage)).toEqual([id(1)]);
});
