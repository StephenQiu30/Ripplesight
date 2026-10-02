// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { ItemReader } from "@/app/items/[contentId]/components/item-reader";
import { savedIds } from "@/components/publication/local-reading";

afterEach(() => {
  cleanup();
  localStorage.clear();
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
