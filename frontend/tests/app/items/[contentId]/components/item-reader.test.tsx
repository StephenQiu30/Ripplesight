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

const editorState = vi.hoisted(() => ({
  saved: null as import("@/components/editor").EditorDocument | null,
}));
vi.mock("@/components/editor/editor", async () => {
  const { useImperativeHandle } = await import("react");
  const { documentToText, textToDocument } =
    await import("@/components/editor/content");
  return {
    Editor: ({
      value,
      onChange,
      ref,
      ...props
    }: import("@/components/editor").EditorProps) => {
      useImperativeHandle(
        ref,
        () => ({ save: async () => editorState.saved ?? value }),
        [value],
      );
      return (
        <textarea
          id={props.id}
          aria-labelledby={props["aria-labelledby"]}
          value={documentToText(value)}
          onChange={(event) => onChange?.(textToDocument(event.target.value))}
        />
      );
    },
  };
});

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
  editorState.saved = null;
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

it("restores the saved reading position, note and translation inside the layout scroll container", async () => {
  localStorage.setItem(
    readingKey,
    JSON.stringify({
      note: "继续阅读这篇资讯",
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
    expect(
      (
        screen.getByRole("textbox", {
          name: "本机阅读笔记",
        }) as HTMLTextAreaElement
      ).value,
    ).toBe("继续阅读这篇资讯");
    expect(screen.getByText("部分中文")).toBeTruthy();
  });

  screen.getByRole("main").scrollTop = 360;
  fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
  await waitFor(() =>
    expect(JSON.parse(localStorage.getItem(readingKey)!)).toMatchObject({
      note: "继续阅读这篇资讯",
      mode: "translated",
      scroll: 360,
    }),
  );
});

it("saves the current main reading position with the note and block document", async () => {
  render(
    <BasicLayout>
      <ItemReader item={item} />
    </BasicLayout>,
  );
  screen.getByRole("main").scrollTop = 360;
  fireEvent.change(screen.getByRole("textbox", { name: "本机阅读笔记" }), {
    target: { value: "记下当前进展" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));

  await waitFor(() =>
    expect(JSON.parse(localStorage.getItem(readingKey)!)).toMatchObject({
      note: "记下当前进展",
      mode: "original",
      scroll: 360,
    }),
  );
});

it("preserves the main reading position on pagehide and when the reader unmounts", async () => {
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
  fireEvent.change(screen.getByRole("textbox", { name: "本机阅读笔记" }), {
    target: { value: "下次继续" },
  });
  fireEvent(window, new Event("pagehide"));

  expect(JSON.parse(localStorage.getItem(readingKey)!)).toMatchObject({
    note: "下次继续",
    mode: "original",
    scroll: 360,
  });

  main.scrollTop = 520;
  view.unmount();

  expect(JSON.parse(localStorage.getItem(readingKey)!)).toMatchObject({
    note: "下次继续",
    mode: "original",
    scroll: 520,
  });
});

it("stores the latest ref.save result even before onChange publishes it", async () => {
  localStorage.setItem(
    readingKey,
    JSON.stringify({ note: "旧笔记", mode: "original", scroll: 0 }),
  );
  render(<ItemReader item={item} />);
  await waitFor(() =>
    expect(
      (
        screen.getByRole("textbox", {
          name: "本机阅读笔记",
        }) as HTMLTextAreaElement
      ).value,
    ).toBe("旧笔记"),
  );
  editorState.saved = {
    blocks: [{ type: "header", data: { text: "刚刚输入", level: 2 } }],
  };
  fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
  await waitFor(() =>
    expect(JSON.parse(localStorage.getItem(readingKey)!).note).toBe("刚刚输入"),
  );
  fireEvent(window, new Event("pagehide"));
  expect(
    JSON.parse(localStorage.getItem(readingKey)!).noteDocument.blocks[0].type,
  ).toBe("header");
});

it("does not overwrite a saved note with content over the limit on save or pagehide", async () => {
  localStorage.setItem(
    readingKey,
    JSON.stringify({ note: "已保存", mode: "original", scroll: 0 }),
  );
  const view = render(<ItemReader item={item} />);
  const textbox = screen.getByRole("textbox", { name: "本机阅读笔记" });
  await waitFor(() =>
    expect((textbox as HTMLTextAreaElement).value).toBe("已保存"),
  );
  fireEvent.change(textbox, { target: { value: "长".repeat(2001) } });
  fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith(
      "笔记最多 2000 字，请缩短后保存。",
    ),
  );
  fireEvent(window, new Event("pagehide"));
  view.unmount();
  expect(JSON.parse(localStorage.getItem(readingKey)!).note).toBe("已保存");
});
