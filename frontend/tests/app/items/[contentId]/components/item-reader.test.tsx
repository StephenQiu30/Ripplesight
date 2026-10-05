// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const notifications = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications, Toaster: () => null }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/items/00000000-0000-4000-8000-000000000001",
}));

import { ItemReader } from "@/app/items/[contentId]/components/item-reader";
import { savedIds } from "@/components/publication/local-reading";
import { BasicLayout } from "@/layout/basic-layout";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
  localStorage.clear();
  window.scrollTo(0, 0);
});

const item: HotKeyAPI.PublicItemDetailView = {
  id: "00000000-0000-4000-8000-000000000001",
  revision: 1,
  title: "公开资讯",
  original_title: null,
  summary: "当前摘要",
  source: { key: "official", name: "官方来源", kind: "rss", first_party: true },
  original_url: "https://example.com/article",
  reading_url: "/items/fixed",
  published_at: null,
  discovered_at: "2026-10-02T01:00:00Z",
  timeline_at: "2026-10-02T01:00:00Z",
  category: null,
  tags: [],
  score: null,
  selected: true,
  reason: null,
  event_id: null,
  fact_id: null,
  indexable: false,
  reading_mode: "full",
  site_fulltext: true,
  syndicate_fulltext: false,
  markdown_available: true,
  license_name: "明确许可",
  license_url: null,
  body: {
    original: "Original text",
    original_html: "<p>Original text</p>",
    translated: "<p>部分中文</p>",
    translation_state: "partial",
    translation_complete: false,
    outline: [],
    media: [
      {
        key: "image1",
        kind: "image",
        original_url: "https://example.com/image.png",
        reading_url: null,
        state: "original_link",
        alt: "来源图片",
      },
    ],
  },
};

it("labels incomplete translation and never inlines unmirrored supplier media", () => {
  const { container } = render(<ItemReader item={item} />);
  expect(screen.getByText("部分译文")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "中文译文" }));
  expect(screen.getByText(/这份译文尚未完整/)).toBeTruthy();
  expect(screen.getByText("部分中文")).toBeTruthy();
  expect(container.querySelector("img")).toBeNull();
  expect(
    screen.getByRole("link", { name: /来源图片/ }).getAttribute("href"),
  ).toBe("https://example.com/image.png");
});

it("summary-only renders no old body/export and stores only an ID when saved", () => {
  render(
    <ItemReader
      item={{
        ...item,
        body: null,
        reading_mode: "summary-only",
        site_fulltext: false,
        markdown_available: false,
      }}
    />,
  );
  expect(screen.queryByText("Original text")).toBeNull();
  expect(screen.queryByRole("link", { name: "下载 Markdown" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "本机收藏" }));
  expect(savedIds(localStorage)).toEqual([item.id]);
  expect(localStorage.getItem("hotkey.publication.saved.v1")).not.toContain(
    item.title,
  );
});

it("rejects invalid local saved material instead of trusting it as public content", () => {
  expect(
    savedIds({
      getItem: () =>
        JSON.stringify([
          item.id,
          item.id,
          "https://attacker.example",
          {},
          null,
        ]),
    }),
  ).toEqual([item.id]);
  expect(savedIds({ getItem: () => "broken" })).toEqual([]);
});

const readingKey = `hotkey.reading.v1.${item.id}.${item.revision}`;

it("reports clipboard denial through Sonner without adding a footer message", async () => {
  const clipboard = vi
    .spyOn(navigator.clipboard, "writeText")
    .mockRejectedValue(new Error("denied"));
  render(<ItemReader item={item} />);
  fireEvent.click(screen.getByRole("button", { name: "复制阅读链接" }));
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith(
      "暂时无法复制，请复制浏览器地址。",
    ),
  );
  expect(clipboard).toHaveBeenCalledOnce();
  expect(screen.queryByText("暂时无法复制，请复制浏览器地址。")).toBeNull();
});

it("restores reading position and translation while ignoring legacy notes", async () => {
  localStorage.setItem(
    readingKey,
    JSON.stringify({
      note: "旧笔记",
      noteDocument: {
        blocks: [{ type: "paragraph", data: { text: "旧笔记" } }],
      },
      mode: "translated",
      scroll: 480,
    }),
  );
  render(
    <BasicLayout>
      <ItemReader item={item} />
    </BasicLayout>,
  );
  await waitFor(() => {
    expect(screen.getByRole("main").scrollTop).toBe(480);
    expect(screen.getByText("部分中文")).toBeTruthy();
  });
  expect(screen.queryByText("本机阅读笔记")).toBeNull();
  expect(screen.queryByRole("button", { name: "保存笔记" })).toBeNull();
  expect(screen.queryByRole("textbox")).toBeNull();
  screen.getByRole("main").scrollTop = 360;
  fireEvent(window, new Event("pagehide"));
  expect(JSON.parse(localStorage.getItem(readingKey)!)).toEqual({
    mode: "translated",
    scroll: 360,
  });
});

it("preserves reading position on pagehide and unmount without storing notes", async () => {
  const view = render(
    <BasicLayout>
      <ItemReader item={item} />
    </BasicLayout>,
  );
  await new Promise((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(resolve)),
  );
  const main = screen.getByRole("main");
  main.scrollTop = 360;
  fireEvent(window, new Event("pagehide"));
  expect(JSON.parse(localStorage.getItem(readingKey)!)).toEqual({
    mode: "original",
    scroll: 360,
  });
  main.scrollTop = 520;
  view.unmount();
  expect(JSON.parse(localStorage.getItem(readingKey)!)).toEqual({
    mode: "original",
    scroll: 520,
  });
});

it("keeps reading available when saved state is corrupt or local storage is blocked", async () => {
  localStorage.setItem(readingKey, "broken-json");
  const view = render(
    <BasicLayout>
      <ItemReader item={item} />
    </BasicLayout>,
  );
  await new Promise((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(resolve)),
  );
  expect(screen.getByText("Original text")).toBeTruthy();
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("denied");
  });
  fireEvent(window, new Event("pagehide"));
  view.unmount();
  expect(notifications.error).not.toHaveBeenCalled();
});
