// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { DiscoveryFilters } from "@/app/discover/components/discovery-filters";
import { selectOption } from "../../../select";

afterEach(cleanup);
it("submits the existing query fields and returns category/channel to empty values", async () => {
  render(
    <DiscoveryFilters
      mode="selected"
      window="24h"
      by="timeline"
      category="paper"
      channel="news"
      params={{ q: "主题", source_key: "rss" }}
      categories={[
        ["paper", "论文"],
        ["industry", "行业"],
      ]}
    />,
  );
  const form = screen.getByRole("button", { name: "搜索" }).closest("form")!;
  expect(new FormData(form).get("category")).toBe("paper");
  expect(new FormData(form).get("channel")).toBe("news");
  fireEvent.click(screen.getByRole("radio", { name: "全部分类" }));
  await selectOption(screen.getByLabelText("频道"), "全部频道");
  await waitFor(() => {
    const query = new FormData(form);
    expect(query.get("category")).toBe("");
    expect(query.get("channel")).toBe("");
    expect(query.get("mode")).toBe("selected");
    expect(query.get("window")).toBe("24h");
    expect(query.get("by")).toBe("timeline");
    expect(query.get("q")).toBe("主题");
    expect(query.get("source_key")).toBe("rss");
    expect(query.get("cursor")).toBeNull();
  });
});

it("keeps a single selection, submits the scope and time, and removes an old cursor", async () => {
  render(
    <DiscoveryFilters
      mode="all"
      window="24h"
      by="timeline"
      params={{
        q: "研究",
        cursor: "old-page",
        tag: "研究",
        topic: "research",
        search_order: "time",
      }}
      categories={[["paper", "论文"]]}
    />,
  );
  const form = screen.getByRole("search", {
    name: "公开资讯检索",
  }) as HTMLFormElement;
  fireEvent.click(screen.getByRole("radio", { name: "论文" }));
  fireEvent.click(screen.getByRole("radio", { name: "论文" }));
  fireEvent.click(screen.getByRole("radio", { name: "精选" }));
  await selectOption(screen.getByLabelText("时间"), "过去 7 天");
  const query = new FormData(form);
  expect(form.getAttribute("action")).toBe("/discover");
  expect(form.getAttribute("method")).toBe("get");
  expect(query.get("category")).toBe("paper");
  expect(query.get("mode")).toBe("selected");
  expect(query.get("window")).toBe("7d");
  expect(query.get("q")).toBe("研究");
  expect(query.get("tag")).toBe("研究");
  expect(query.get("topic")).toBe("research");
  expect(query.get("search_order")).toBe("time");
  expect(query.get("cursor")).toBeNull();
  expect(
    screen.getByRole("radiogroup", { name: "分类" }).parentElement?.className,
  ).toContain("hide-scrollbar");
});

it("shows readable source names while submitting stable keys and supports all sources", async () => {
  render(
    <DiscoveryFilters
      mode="all"
      window="7d"
      by="timeline"
      params={{ source_key: "ed_rss_example" }}
      categories={[]}
      sources={[
        { key: "ed_rss_example", name: "arXiv 研究" },
        { key: "ed_json_example", name: "Crossref 元数据" },
      ]}
    />,
  );
  const source = screen.getByLabelText("来源");
  expect(source.textContent).toContain("arXiv 研究");
  expect(source.textContent).not.toContain("ed_rss_example");
  const form = screen.getByRole("button", { name: "搜索" }).closest("form")!;
  await selectOption(source, "Crossref 元数据");
  expect(new FormData(form).get("source_key")).toBe("ed_json_example");
  await selectOption(source, "全部来源");
  expect(new FormData(form).get("source_key")).toBe("");
});

it("keeps advanced form values when filters are collapsed and restores the draft on reopen", () => {
  render(
    <DiscoveryFilters
      mode="all"
      window="7d"
      by="timeline"
      params={{}}
      categories={[]}
    />,
  );
  const toggle = screen.getByRole("button", { name: "高级筛选" });
  const form = screen.getByRole("button", { name: "搜索" }).closest("form")!;
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  expect(new FormData(form).get("by")).toBe("timeline");
  expect(new FormData(form).get("search_order")).toBe("relevance");
  fireEvent.click(toggle);
  fireEvent.change(screen.getByLabelText("标签"), {
    target: { value: "研究" },
  });
  fireEvent.click(toggle);
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  expect(new FormData(form).get("tag")).toBe("研究");
  fireEvent.click(toggle);
  expect(screen.getByLabelText<HTMLInputElement>("标签").value).toBe("研究");
});
