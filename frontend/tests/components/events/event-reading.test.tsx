// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  EventSources,
  FactSummary,
  RepresentativeComments,
} from "@/components/events/event-reading";
import { HeatHistory } from "@/components/events/heat-history";
import {
  eventSourceAnchor,
  publicSources,
} from "@/components/events/reading-model";
import { heat, publicItem } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("links fact numbers to focusable source rows inside a keyboard scroll region", () => {
  const sources = publicSources([publicItem()]);
  render(
    <>
      <FactSummary title="有来源的事实" sources={sources} />
      <EventSources sources={sources} />
    </>,
  );
  expect(
    screen.getByRole("link", { name: "来源 1" }).getAttribute("href"),
  ).toBe(`#${eventSourceAnchor("public-item")}`);
  const region = screen.getByRole("region", { name: "事件来源表，可横向滚动" });
  expect(region.tabIndex).toBe(0);
  expect(region.querySelector("table")).toBeTruthy();
  expect(
    region
      .querySelector(`#${eventSourceAnchor("public-item")}`)
      ?.getAttribute("tabindex"),
  ).toBe("-1");
  expect(screen.getByRole("link", { name: "原文" }).getAttribute("rel")).toBe(
    "noopener noreferrer",
  );
});

it("renders none, unavailable and readable comments as different states and keeps comment text inert", () => {
  render(
    <RepresentativeComments
      comments={[
        {
          id: "none",
          source: "A",
          state: "none",
          body: null,
          time: null,
          originalUrl: null,
        },
        {
          id: "unavailable",
          source: "B",
          state: "unavailable",
          body: null,
          time: null,
          originalUrl: null,
        },
        {
          id: "readable",
          source: "C",
          state: "readable",
          body: "<script>评论原文</script>",
          time: "2026-10-02T01:00:00Z",
          originalUrl: "https://source.example/comment",
        },
      ]}
    />,
  );
  expect(screen.getByText("此来源尚无代表评论。")).toBeTruthy();
  expect(screen.getByText("代表评论证据暂不可读。")).toBeTruthy();
  expect(screen.getByText("<script>评论原文</script>")).toBeTruthy();
  expect(screen.getByText(/评论未固定到事件成员版本/)).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "评论原文" }).getAttribute("href"),
  ).toBe("https://source.example/comment");
  expect(document.querySelector("script")).toBeNull();
  expect(screen.queryByText(/情感分布|负面占比/)).toBeNull();
});

it("does not draw a chart for absent or insufficient actual history", () => {
  const { rerender, container } = render(<HeatHistory history={[]} />);
  expect(screen.getByText(/尚无当前修订的实际小时快照/)).toBeTruthy();
  expect(container.querySelector('[data-slot="chart"]')).toBeNull();
  rerender(<HeatHistory history={[heat()]} />);
  expect(screen.getByText(/样本不足，不绘制折线/)).toBeTruthy();
  expect(container.querySelector('[data-slot="chart"]')).toBeNull();
});

it("hides the chart from assistive technology, gives a truthful summary, and avoids a CSP-blocked inline stylesheet", () => {
  // happy-dom has no layout engine. Give the official responsive chart a
  // measured container instead of replacing its rendered graph with a mock.
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
    new DOMRect(0, 0, 640, 192),
  );
  const { container } = render(
    <HeatHistory
      history={[
        heat("2026-10-02T03:00:00Z", 7),
        heat("2026-10-02T01:00:00Z", 2),
      ]}
    />,
  );
  const summary = screen.getByText(
    (_, node) =>
      node?.tagName === "P" && !!node.textContent?.startsWith("热度历史："),
  );
  expect(summary.textContent).toContain("共 2 个实际快照");
  expect(summary.textContent).toContain("热度从 2.0 到 7.0");
  expect(summary.textContent).toContain("最高 7.0");
  expect(
    container
      .querySelector('[data-slot="chart"]')
      ?.parentElement?.getAttribute("aria-hidden"),
  ).toBe("true");
  expect(container.querySelector("style")).toBeNull();
  expect(container.querySelector("svg")).toBeTruthy();
});
