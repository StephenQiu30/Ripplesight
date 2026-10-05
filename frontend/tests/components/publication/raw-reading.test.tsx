// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import {
  PublicItemCards,
  PublicSourceStatus,
} from "@/components/publication/reading-parts";

afterEach(cleanup);

const item: HotKeyAPI.PublicItemView = {
  id: "raw-item",
  revision: 1,
  title: "Original research title",
  original_title: null,
  summary: null,
  source: { key: "source", name: "Research", kind: "rss", first_party: false },
  original_url: "https://example.com/paper",
  reading_url: "/items/raw-item",
  published_at: null,
  discovered_at: "2026-10-03T18:00:00Z",
  timeline_at: "2026-10-03T18:00:00Z",
  category: null,
  tags: [],
  score: null,
  selected: false,
  reason: null,
  event_id: null,
  fact_id: null,
  indexable: false,
  analysis_state: "not_analyzed",
  summary_origin: "none",
};

it("keeps original access and identifies discovery time without inventing an abstract or selection", () => {
  render(<PublicItemCards items={[item]} />);
  expect(screen.getByText("未分析")).toBeTruthy();
  expect(screen.getByText(/发现于/)).toBeTruthy();
  expect(screen.getByText("来源未提供摘要，可前往原文阅读。")).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "来源原文" }).getAttribute("href"),
  ).toBe(item.original_url);
  expect(screen.queryByText("精选")).toBeNull();
});

it("distinguishes a licensed source abstract from generated writing", () => {
  render(
    <PublicItemCards
      items={[
        { ...item, summary: "Original abstract", summary_origin: "source" },
      ]}
    />,
  );
  expect(screen.getByText("来源摘要：")).toBeTruthy();
  expect(screen.getByText(/Original abstract/)).toBeTruthy();
  expect(screen.queryByText(/来源未提供摘要/)).toBeNull();
});

it("shows persistent paused-source status with the last success while keeping saved reading available", () => {
  render(
    <PublicSourceStatus
      sources={[
        {
          source_key: "source",
          name: "Research",
          enabled: false,
          health: "ok",
          last_success_at: item.discovered_at,
        },
      ]}
    />,
  );
  expect(screen.getByRole("alert").textContent).toContain("已暂停");
  expect(screen.getByText(/最近成功/)).toBeTruthy();
  expect(
    screen.getByText("已保存且许可仍有效的资讯可以继续阅读。"),
  ).toBeTruthy();
});
