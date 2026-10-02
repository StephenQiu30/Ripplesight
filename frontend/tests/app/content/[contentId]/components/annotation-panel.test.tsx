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
