// @vitest-environment happy-dom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  detail: vi.fn(),
  members: vi.fn(),
  facts: vi.fn(),
  correct: vi.fn(),
  events: vi.fn(),
  push: vi.fn(),
}));
vi.mock("@/api/shijian", () => ({
  getEvent: api.detail,
  listEventMembers: api.members,
  listEventFacts: api.facts,
  correctEvent: api.correct,
  listEvents: api.events,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push }) }));
vi.mock("@/components/navigation/workspace-header", () => ({
  WorkspaceHeader: () => <nav>工作区导航</nav>,
}));

vi.mock("./event-heat", () => ({ EventHeat: () => null }));

import { EventDetail } from "./event-detail";
import { ApiRequestError } from "@/request";

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
beforeEach(() => {
  api.facts.mockResolvedValue({ facts: [] });
  api.events.mockResolvedValue({ items: [], next_cursor: null });
});

describe("fixed event member reading", () => {
  it("uses the canonical identity and fixed revision, renders real body and keeps unknown counts", async () => {
    api.detail.mockResolvedValue({
      id: "canonical-event",
      topic_id: "topic",
      revision: 2,
      title: null,
      summary: null,
      first_seen_at: "2026-10-02T00:00:00Z",
      first_seen_basis: "published",
      source_counts: { hackernews: 2 },
      member_count: 2,
      readable_member_count: 1,
      evidence_state: "partial",
      derived_text_available: false,
      redirected_from_event_id: "old-event",
    });
    api.members.mockResolvedValue({
      event_id: "canonical-event",
      revision: 2,
      current_revision: 2,
      evidence_state: "partial",
      next_cursor: null,
      items: [
        {
          id: "member-1",
          content_id: "content",
          content_version_id: "fixed-version",
          source_key: "hackernews",
          availability: "readable",
          assignment_origin: "model",
          added_revision: 1,
          removed_revision: null,
          content: {
            id: "content",
            source_key: "hackernews",
            object_type: "post",
            external_id: "post-1",
            native_scope: null,
            identity_basis: null,
            current_visibility: null,
            representative_comment: null,
            representative_comment_state: "unavailable",
            observation: {
              id: "obs",
              observed_at: "2026-10-02T00:00:00Z",
              received_at: "2026-10-02T00:01:00Z",
              published_at: null,
              canonical_url: "javascript:alert(1)",
              final_url: null,
              author_external_id: "author",
              metrics: {
                like_count: 0,
                comment_count: null,
                repost_count: null,
                view_count: null,
                play_count: null,
                danmaku_count: null,
              },
              content_version: {
                id: "fixed-version",
                text_scope: "full",
                text_origin: "source",
                text_origin_ref: null,
                title: "固定标题",
                body: "<script>固定正文</script>",
                truncation_reason: null,
                relations: [],
              },
            },
          },
        },
        { id: "member-2", availability: "unavailable", content: null },
      ],
    });
    render(<EventDetail eventId="old-event" />);
    expect(await screen.findByText("<script>固定正文</script>")).toBeTruthy();
    await waitFor(() =>
      expect(api.members).toHaveBeenCalledWith(
        expect.objectContaining({ event_id: "canonical-event", revision: 2 }),
        expect.anything(),
      ),
    );
    expect(screen.getByText("已合并到当前事件")).toBeTruthy();
    expect(screen.getByText("评论：未知")).toBeTruthy();
    expect(screen.getByText("点赞：0")).toBeTruthy();
    expect(screen.getByText("该成员证据暂不可读")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "阅读原文" })).toBeNull();
    expect(document.querySelector("script")).toBeNull();
  });

  it("keeps revision selection and member pagination bound to the chosen snapshot", async () => {
    api.detail.mockResolvedValue({
      id: "event",
      revision: 2,
      title: "历史事件",
      summary: null,
      first_seen_at: "2026-10-02T00:00:00Z",
      first_seen_basis: "discovered",
      source_counts: {},
      member_count: 2,
      readable_member_count: 2,
      evidence_state: "complete",
      derived_text_available: false,
    });
    api.members
      .mockResolvedValueOnce({
        items: [],
        event_id: "event",
        revision: 2,
        current_revision: 2,
        evidence_state: "complete",
        next_cursor: "next-members",
      })
      .mockResolvedValue({
        items: [],
        event_id: "event",
        revision: 1,
        current_revision: 2,
        evidence_state: "complete",
        next_cursor: null,
      });
    render(<EventDetail eventId="event" />);
    fireEvent.click(
      await screen.findByRole("button", { name: "加载更多成员" }),
    );
    await waitFor(() =>
      expect(api.members).toHaveBeenLastCalledWith(
        expect.objectContaining({
          event_id: "event",
          revision: 2,
          cursor: "next-members",
        }),
        expect.anything(),
      ),
    );
    fireEvent.change(screen.getByLabelText("事件修订"), {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "读取该修订成员" }));
    await waitFor(() =>
      expect(api.members).toHaveBeenLastCalledWith(
        expect.objectContaining({ event_id: "event", revision: 1 }),
        expect.anything(),
      ),
    );
    expect(await screen.findByText("当前展示历史成员")).toBeTruthy();
  });

  it("shows unreadable events as 404 and retries through the generated API", async () => {
    api.detail.mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        code: "resource_not_found",
        status: 404,
        message: "请求资源不存在",
      }),
    );
    render(<EventDetail eventId="missing-event" />);
    expect(
      await screen.findByRole("heading", { name: "事件不存在或暂不可读" }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重试事件详情" }));
    await waitFor(() => expect(api.detail).toHaveBeenCalledTimes(2));
    expect(api.members).not.toHaveBeenCalled();
  });
});
