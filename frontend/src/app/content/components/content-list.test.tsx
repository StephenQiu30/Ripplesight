import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  ContentAnalysisStatus,
  TimelineBasis,
  contentListParams,
} from "./content-list";

const filters = {
  sourceKey: "hn_algolia",
  topicId: "d0e34b3d-e2b5-4c32-8436-741ca2015cc1",
  startDate: "2026-09-27",
  endDate: "2026-09-28",
  analysisState: "pending" as const,
};

const content: HotKeyAPI.ContentRecordSummaryView = {
  id: "af79ab61-5fe5-46af-91dd-b4103242a2ec",
  source_key: "hn_algolia",
  object_type: "post",
  native_scope: null,
  external_id: "controlled-1",
  identity_basis: null,
  latest_observation: {
    id: "0cc7354b-2e0c-4634-aaf1-26b8805cccaa",
    observed_at: "2026-09-28T08:00:00Z",
    received_at: "2026-09-28T08:00:00Z",
    published_at: null,
    published_at_fractional_digits: null,
    canonical_url: null,
    final_url: null,
    author_external_id: null,
    metrics: {
      like_count: null,
      comment_count: null,
      repost_count: null,
      view_count: null,
      play_count: null,
      danmaku_count: null,
    },
    content_version: null,
  },
  current_visibility: null,
  discovery_count: 1,
  timeline_at: "2026-09-28T07:00:00Z",
  timeline_basis: "first_observed_at",
  analysis_state: "pending",
  analysis_relevant: null,
};

describe("content list filters", () => {
  it("converts inclusive Beijing dates into a half-open UTC window and retains the cursor", () => {
    expect(contentListParams(filters, "page-two")).toEqual({
      source_key: "hn_algolia",
      topic_id: filters.topicId,
      starts_at: "2026-09-26T16:00:00.000Z",
      ends_at: "2026-09-28T16:00:00.000Z",
      analysis_state: "pending",
      cursor: "page-two",
      limit: 20,
    });
  });

  it("rejects incomplete, reversed, excessive and topicless state filters", () => {
    expect(() => contentListParams({ ...filters, endDate: "" })).toThrow(
      "完整",
    );
    expect(() =>
      contentListParams({ ...filters, endDate: "2026-09-26" }),
    ).toThrow("最多 31 天");
    expect(() =>
      contentListParams({ ...filters, endDate: "2026-10-29" }),
    ).toThrow("最多 31 天");
    expect(() => contentListParams({ ...filters, topicId: "" })).toThrow(
      "先选择主题",
    );
  });

  it("shows discovery time and keeps pending distinct from a valid relevance result", () => {
    expect(
      renderToStaticMarkup(createElement(TimelineBasis, { content })),
    ).toContain("首次发现");
    expect(
      renderToStaticMarkup(createElement(ContentAnalysisStatus, { content })),
    ).toContain("等待标注");
    const valid = { ...content, analysis_state: "valid" as const };
    expect(
      renderToStaticMarkup(
        createElement(ContentAnalysisStatus, {
          content: { ...valid, analysis_relevant: false },
        }),
      ),
    ).toContain("不相关");
    expect(
      renderToStaticMarkup(
        createElement(ContentAnalysisStatus, {
          content: { ...content, analysis_state: "missing" },
        }),
      ),
    ).toContain("暂无标注记录");
  });
});
