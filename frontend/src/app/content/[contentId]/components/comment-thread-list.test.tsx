import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  CommentCard,
  parentRelationLabel,
  replyContext,
} from "./comment-thread-list";
import {
  CommentRefreshControls,
  CommentRefreshOperation,
} from "./comment-refresh-action";

const observation: HotKeyAPI.ContentObservationView = {
  id: "ab15d0c1-0b72-4c3a-9e1b-0adf218d7d30",
  observed_at: "2026-09-27T08:00:00Z",
  received_at: "2026-09-27T08:00:00Z",
  published_at: null,
  published_at_fractional_digits: null,
  canonical_url: "javascript:alert(1)",
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
  content_version: {
    id: "7a89dc2d-5db2-4f7e-9b2d-476cc34621f3",
    text_scope: "full",
    text_origin: "source",
    text_origin_ref: null,
    title: null,
    body: "<script>alert('bad')</script>",
    truncation_reason: null,
    relations: [],
  },
};

const reply: HotKeyAPI.ContentCommentView = {
  content_id: "a1549683-e5b5-46c4-9c38-2d3466cc299a",
  external_id: "reply-1",
  root_content_id: "46e89288-8e8f-4415-a5f7-cbff60518325",
  parent_content_id: "91a8c92a-9113-40de-bc53-f985345465a1",
  reply_target_content_id: "91a8c92a-9113-40de-bc53-f985345465a1",
  parent_relation_status: "unavailable",
  latest_observation: observation,
  has_replies: false,
};

describe("comment thread reading", () => {
  it("keeps a single operation ID through double click and retry", () => {
    const operation = new CommentRefreshOperation(() => "fixed-operation-id");
    expect(operation.begin()).toBe("fixed-operation-id");
    expect(operation.begin()).toBeNull();
    operation.finish(false);
    expect(operation.begin()).toBe("fixed-operation-id");
    operation.finish(true);
    expect(operation.begin()).toBeNull();
  });

  it("only shows the refresh action when supported and disables limited requests", () => {
    const unsupported = renderToStaticMarkup(
      createElement(CommentRefreshControls, {
        readiness: {
          supported: false,
          available: false,
          reason: "comments_not_ready",
        },
        submitting: false,
        message: null,
        onRefresh: () => {},
      }),
    );
    expect(unsupported).not.toContain("更新评论");

    const limited = renderToStaticMarkup(
      createElement(CommentRefreshControls, {
        readiness: {
          supported: true,
          available: false,
          reason: "comments_rate_limited",
        },
        submitting: false,
        message: null,
        onRefresh: () => {},
      }),
    );
    expect(limited).toContain("disabled");
    expect(limited).toContain("间隔期");

    const pending = renderToStaticMarkup(
      createElement(CommentRefreshControls, {
        readiness: { supported: true, available: true, reason: null },
        submitting: true,
        message: null,
        onRefresh: () => {},
      }),
    );
    expect(pending).toContain("正在受理");
    expect(pending).toContain("disabled");
  });

  it("renders source text safely and keeps the missing-parent notice", () => {
    const html = renderToStaticMarkup(
      createElement(CommentCard, { comment: reply }),
    );

    expect(html).toContain("直接父评论无正文或不可读");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("javascript:");
    expect(html).toContain("点赞 未知");
  });

  it("keeps an unreadable root as a relationship placeholder", () => {
    const html = renderToStaticMarkup(
      createElement(CommentCard, {
        comment: {
          ...reply,
          external_id: null,
          parent_content_id: null,
          reply_target_content_id: null,
          parent_relation_status: "unresolved",
          latest_observation: null,
          has_replies: true,
        },
      }),
    );

    expect(html).toContain("关系占位");
    expect(html).toContain("父链尚未确认");
    expect(html).toContain("暂无可读正文");
    expect(html).not.toContain("评论 reply-1");
    expect(parentRelationLabel("root")).toBeNull();
  });

  it("names a visible direct parent without inventing a missing ancestor", () => {
    const root: HotKeyAPI.ContentCommentView = {
      ...reply,
      content_id: reply.root_content_id!,
      external_id: "root-1",
      parent_content_id: null,
      reply_target_content_id: null,
      parent_relation_status: "root",
    };
    expect(
      replyContext(
        { ...reply, parent_content_id: root.content_id },
        root,
        new Map(),
      ),
    ).toBe("回复线程根 root-1");
    expect(
      replyContext(
        { ...reply, parent_relation_status: "observed" },
        root,
        new Map(),
      ),
    ).toBe("直接父评论未在本页显示");
    expect(replyContext(reply, root, new Map())).toBeNull();
  });
});
