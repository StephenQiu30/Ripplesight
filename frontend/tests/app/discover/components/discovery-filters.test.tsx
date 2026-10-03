// @vitest-environment happy-dom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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
  const form = screen.getByRole("button", { name: "查看" }).closest("form")!;
  expect(new FormData(form).get("category")).toBe("paper");
  expect(new FormData(form).get("channel")).toBe("news");
  await selectOption(screen.getByLabelText("分类"), "全部分类");
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
  const form = screen.getByRole("button", { name: "查看" }).closest("form")!;
  await selectOption(source, "Crossref 元数据");
  expect(new FormData(form).get("source_key")).toBe("ed_json_example");
  await selectOption(source, "全部来源");
  expect(new FormData(form).get("source_key")).toBe("");
});
