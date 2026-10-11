import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  AnnotationResult,
  selectedAnnotation,
} from "@/app/content/[contentId]/components/annotation-panel";

const topic: HotKeyAPI.ContentAnalysisTopicView = {
  topic_id: "7e58ebff-077b-4c80-88dc-a60d72ec75e2",
  topic_name: "品牌召回",
  current_rule_version: 2,
};

const pending: HotKeyAPI.ContentAnnotationReadView = {
  id: "81881347-75b6-46df-8d83-46c5cf05a4f8",
  topic_id: topic.topic_id,
  content_version_id: "5b07bd1f-67d8-4aa2-9772-8ad0ea489819",
  topic_rule_version: 2,
  prompt_version: "analysis.annotate.v1",
  status: "unanalyzed",
  result_state: "pending",
  relevant: null,
  relevance_reason: null,
  sentiment: null,
  summary: null,
  viewpoints: [],
  error_code: null,
  updated_at: "2026-09-28T08:00:00Z",
};

describe("content annotation reading", () => {
  it("keeps a stale valid result separate from the current pending state", () => {
    const stale: HotKeyAPI.ContentAnnotationReadView = {
      ...pending,
      id: "32a1c0d4-8153-46ea-b975-57df3a975e23",
      topic_rule_version: 1,
      status: "annotated",
      result_state: "valid",
      relevant: true,
      relevance_reason: "旧规则理由",
      sentiment: "neutral",
      summary: "旧规则摘要",
    };
    const oldPrompt = {
      ...stale,
      id: "a728baad-5d49-4d3c-8c7e-c22a14fb3e7a",
      topic_rule_version: 2,
      prompt_version: "analysis.annotate.previous",
    };
    const selected = selectedAnnotation(
      [stale, oldPrompt, pending],
      topic,
      pending.content_version_id,
      pending.prompt_version,
    );
    expect(selected.current).toEqual(pending);
    expect(selected.historical).toEqual([stale, oldPrompt]);
    expect(
      selectedAnnotation(
        [stale],
        topic,
        pending.content_version_id,
        pending.prompt_version,
      ).current,
    ).toBeNull();
    expect(
      selectedAnnotation(
        [stale],
        topic,
        "another-version",
        pending.prompt_version,
      ).historical,
    ).toEqual([]);
  });

  it("shows missing, pending, failed and invalid without inventing a relevance result", () => {
    const missing = renderToStaticMarkup(
      createElement(AnnotationResult, { annotation: null, historical: false }),
    );
    expect(missing).toContain("暂无标注记录");
    expect(missing).toContain("不能将无记录当作不相关");
    for (const [state, label] of [
      ["pending", "等待标注"],
      ["failed", "标注失败"],
      ["invalid", "标注无效"],
    ] as const) {
      const html = renderToStaticMarkup(
        createElement(AnnotationResult, {
          annotation: {
            ...pending,
            result_state: state,
            error_code: state === "pending" ? null : "controlled_error",
          },
          historical: false,
        }),
      );
      expect(html).toContain(label);
      expect(html).not.toContain("判断理由：");
    }
  });

  it("escapes external analysis text and labels valid relevance explicitly", () => {
    const html = renderToStaticMarkup(
      createElement(AnnotationResult, {
        annotation: {
          ...pending,
          status: "annotated",
          result_state: "valid",
          relevant: false,
          relevance_reason: "<script>alert(1)</script>",
          summary: "受控摘要",
          viewpoints: ["<img src=x onerror=alert(1)>"],
        },
        historical: true,
      }),
    );
    expect(html).toContain("不相关");
    expect(html).toContain("历史结果");
    expect(html).not.toContain("情感：");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<img");
  });
});

it("retains valid v1 and prefers valid v2 even when a v1 arrives later", () => {
  const legacy: HotKeyAPI.ContentAnnotationReadView = {
    ...pending,
    prompt_version: "analysis.annotate.v1",
    status: "annotated",
    result_state: "valid",
    relevant: true,
    relevance_reason: "旧有效判断",
    summary: "旧摘要",
    updated_at: "2026-10-10T00:00:00Z",
  };
  const current: HotKeyAPI.ContentAnnotationReadView = {
    ...legacy,
    id: "f20e7260-1cab-4766-b40c-bb0a8157b666",
    prompt_version: "analysis.annotate.v2",
    relevant: false,
    updated_at: "2026-10-09T00:00:00Z",
  };
  expect(
    selectedAnnotation(
      [legacy],
      topic,
      pending.content_version_id,
      "analysis.annotate.v2",
    ).current,
  ).toEqual(legacy);
  expect(
    selectedAnnotation(
      [legacy, current],
      topic,
      pending.content_version_id,
      "analysis.annotate.v2",
    ).current,
  ).toEqual(current);
  expect(
    selectedAnnotation(
      [legacy, { ...current, result_state: "pending", relevant: null }],
      topic,
      pending.content_version_id,
      "analysis.annotate.v2",
    ).current,
  ).toEqual(legacy);
  expect(
    selectedAnnotation(
      [{ ...legacy, prompt_version: "unknown" }],
      topic,
      pending.content_version_id,
      "analysis.annotate.v2",
    ).current,
  ).toBeNull();
});

it("shows valid relevance with unanalyzed sentiment without a neutral label", () => {
  const html = renderToStaticMarkup(
    createElement(AnnotationResult, {
      historical: false,
      annotation: {
        ...pending,
        status: "annotated",
        result_state: "valid",
        relevant: true,
        relevance_reason: "直接讨论主题",
        summary: "产品发布",
        sentiment: null,
      },
    }),
  );
  expect(html).toContain("相关");
  expect(html).toContain("情感：未分析");
  expect(html).not.toContain("情感：中性");
});

it("preserves comment insufficient, unknown and deferred without a false conclusion", () => {
  for (const [state, label] of [
    ["insufficient", "信息不足"],
    ["unknown", "未知"],
    ["deferred", "限流延后"],
  ] as const) {
    const html = renderToStaticMarkup(
      createElement(AnnotationResult, {
        annotation: {
          ...pending,
          prompt_version: "analysis.comment.v1",
          result_state: state,
          relevance_reason:
            state === "deferred" ? null : "原帖和可得父评论不足以解释指代",
          error_code: state === "deferred" ? "analysis_rate_limited" : null,
        },
        historical: false,
      }),
    );
    expect(html).toContain(label);
    expect(html).not.toContain("不相关");
    expect(html).not.toContain("情感：");
    expect(html).toContain(
      state === "deferred" ? "冻结输入" : "不足以解释指代",
    );
  }
});

it("shows the newer comment context outcome instead of inheriting an older valid result", () => {
  const previous: HotKeyAPI.ContentAnnotationReadView = {
    ...pending,
    prompt_version: "analysis.comment.v1",
    status: "annotated",
    result_state: "valid",
    relevant: true,
    created_at: "2026-09-27T08:00:00Z",
    updated_at: "2026-09-30T08:00:00Z",
    relevance_reason: "旧父链结论",
    summary: "旧摘要",
  };
  const newer: HotKeyAPI.ContentAnnotationReadView = {
    ...pending,
    id: "new-context",
    prompt_version: "analysis.comment.v1",
    result_state: "insufficient",
    relevance_reason: "父评论版本已变更，当前信息不足",
    created_at: "2026-09-29T08:00:00Z",
    updated_at: "2026-09-29T08:00:00Z",
  };
  const result = selectedAnnotation(
    [previous, newer],
    topic,
    pending.content_version_id,
    "analysis.comment.v1",
  );
  expect(result.current).toEqual(newer);
  expect(result.historical).toEqual([previous]);
});
