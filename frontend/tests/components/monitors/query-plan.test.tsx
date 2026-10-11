import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { QueryPlan } from "@/components/monitors/query-plan";

const plan: HotKeyAPI.KeywordQueryPlanView = {
  version: 1,
  max_queries: 1,
  queries: [
    { query_index: 0, query: "AI", admitted: true, skip_reason: null },
    {
      query_index: 1,
      query: "模型",
      admitted: false,
      skip_reason: "query_limit",
    },
  ],
};

describe("query admission receipt", () => {
  it("shows every omitted query and distinguishes admission from collection", () => {
    const html = renderToStaticMarkup(createElement(QueryPlan, { plan }));
    expect(html).toContain("AI");
    expect(html).toContain("已受理");
    expect(html).toContain("模型");
    expect(html).toContain("未受理（查询上限 1 项）");
    expect(html).toContain("受理不表示已发起请求或完成采集");
    expect(html).toContain("未受理查询不计为零结果");
    expect(html).not.toContain("无结果");
  });

  it("keeps missing historical evidence unknown", () => {
    const html = renderToStaticMarkup(createElement(QueryPlan, { plan: null }));
    expect(html).toContain("未保存逐查询受理记录");
    expect(html).not.toContain("已受理");
  });

  it("explains source skips for each query", () => {
    const html = renderToStaticMarkup(
      createElement(QueryPlan, {
        plan: {
          ...plan,
          max_queries: null,
          queries: plan.queries.map((query) => ({
            ...query,
            admitted: false,
            skip_reason: "budget" as const,
          })),
        },
      }),
    );
    expect(html.match(/未受理（预算不足）/g)).toHaveLength(2);
    expect(html).not.toContain("查询上限");
  });

  it("renders keyword text safely", () => {
    const html = renderToStaticMarkup(
      createElement(QueryPlan, {
        plan: {
          ...plan,
          queries: [{ ...plan.queries[0], query: "<script>alert(1)</script>" }],
        },
      }),
    );
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });
});

it("shows frozen requested and effective bounds with unknown-language limits", () => {
  const html = renderToStaticMarkup(
    createElement(QueryPlan, {
      plan: {
        ...plan,
        collection: {
          topic: {
            search_language: "zh",
            search_window_seconds: 600,
            max_queries: 2,
            max_items_per_query: 8,
            max_requests_per_query: 6,
          },
          starts_at: "2026-10-11T00:00:00Z",
          ends_at: "2026-10-11T00:10:00Z",
          max_items_per_query: 3,
          max_requests_per_query: 1,
        },
      },
    }),
  );
  expect(html).toContain("本地元数据筛选，未知排除");
  expect(html).toContain("2026-10-11T00:00:00Z");
  expect(html).toContain("条候选");
  expect(html).toContain("平台请求");
  expect(html).toContain("达到上限不表示已完整采集");
});
