// @vitest-environment happy-dom
import { expectOnePageHeading } from "../../../../page-heading";

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
  related: vi.fn(),
}));
vi.mock("@/api/shijian", () => ({
  getEvent: api.detail,
  listEventMembers: api.members,
  listEventFacts: api.facts,
  correctEvent: api.correct,
  listEvents: api.events,
  listRelatedEvents: api.related,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push }) }));

vi.mock("@/app/events/[eventId]/components/event-heat", () => ({
  EventHeat: () => null,
}));

import { EventDetail } from "@/app/events/[eventId]/components/event-detail";
import { ApiRequestError } from "@/request";
import { fact, member } from "../../../../components/events/fixtures";

afterEach(() => {
  expectOnePageHeading();
  cleanup();
  vi.resetAllMocks();
});
beforeEach(() => {
  api.facts.mockResolvedValue({ facts: [] });
  api.related.mockResolvedValue({ items: [] });
  api.events.mockResolvedValue({ items: [], next_cursor: null });
});

describe("fixed event member reading", () => {
  it("keeps simultaneous section failures below the event heading", async () => {
    api.detail.mockResolvedValue({
      id: "event",
      topic_id: "topic",
      revision: 1,
      title: "可读事件",
      summary: "摘要",
      first_seen_at: "2026-10-02T00:00:00Z",
      source_counts: {},
      member_count: 0,
      readable_member_count: 0,
      evidence_state: "complete",
    });
    api.facts.mockRejectedValue(new Error("offline"));
    api.members.mockRejectedValue(new Error("offline"));
    api.related.mockRejectedValue(new Error("offline"));
    render(<EventDetail eventId="event" />);
    await waitFor(() => expect(screen.getAllByRole("alert")).toHaveLength(3));
    expectOnePageHeading();
    expect(
      screen.getAllByRole("heading", { level: 2 }).length,
    ).toBeGreaterThanOrEqual(3);
  });
  it("shows the detail loading state before any dependent reads", () => {
    api.detail.mockReturnValue(new Promise(() => {}));
    render(<EventDetail eventId="loading" />);
    expect(
      screen
        .getByRole("status", { name: "正在读取事件详情" })
        .getAttribute("aria-busy"),
    ).toBe("true");
    expectOnePageHeading();
    expect(api.members).not.toHaveBeenCalled();
    expect(api.related).not.toHaveBeenCalled();
  });

  it.each([401, 403])(
    "keeps HTTP %s behind a login state with returnTo",
    async (status) => {
      api.detail.mockRejectedValue(
        new ApiRequestError({
          kind: "http",
          code: "authentication_required",
          status,
          message: "login",
        }),
      );
      render(<EventDetail eventId="private-event" />);
      expect(
        await screen.findByRole("heading", { name: "需要登录后阅读事件" }),
      ).toBeTruthy();
      expect(
        screen.getByRole("link", { name: "登录" }).getAttribute("href"),
      ).toBe("/login?returnTo=%2Fevents%2Fprivate-event");
      expect(screen.getByRole("link", { name: "返回首页" })).toBeTruthy();
      expect(api.members).not.toHaveBeenCalled();
      expect(api.facts).not.toHaveBeenCalled();
      expect(api.related).not.toHaveBeenCalled();
    },
  );

  it("shows the structured error code and retries without hiding it as empty", async () => {
    api.detail.mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        code: "event_read_unavailable",
        status: 503,
        message: "unavailable",
      }),
    );
    render(<EventDetail eventId="failed" />);
    await screen.findByRole("heading", { name: "无法读取事件" });
    expect(screen.getByText("event_read_unavailable · 503")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重试事件详情" }));
    await waitFor(() => expect(api.detail).toHaveBeenCalledTimes(2));
  });

  it("gives every fixed fact reference a source target and keeps correction fields behind the footer control", async () => {
    api.detail.mockResolvedValue({
      id: "event",
      topic_id: "topic",
      revision: 1,
      title: "有事实的事件",
      summary: "摘要",
      first_seen_at: "2026-10-02T00:00:00Z",
      updated_at: "2026-10-03T00:00:00Z",
      source_counts: { controlled: 2 },
      member_count: 2,
      readable_member_count: 2,
      evidence_state: "complete",
    });
    api.facts.mockResolvedValue({
      facts: [fact("loaded-fact", "loaded"), fact("pending-fact", "pending")],
    });
    api.members.mockResolvedValue({
      event_id: "event",
      revision: 1,
      current_revision: 1,
      evidence_state: "complete",
      next_cursor: "more",
      items: [member("loaded")],
    });
    render(<EventDetail eventId="event" />);
    const reference = await screen.findByRole("link", { name: "来源 2" });
    expect(
      document.getElementById(reference.getAttribute("href")!.slice(1))
        ?.textContent,
    ).toContain("此来源尚未加载");
    const first = screen.getByRole("link", { name: "来源 1" });
    expect(
      document.getElementById(first.getAttribute("href")!.slice(1))
        ?.textContent,
    ).toContain("固定标题 loaded");
    expect(screen.queryByRole("textbox", { name: "修订原因" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "人工修订与纠错" }));
    expect(screen.getByLabelText("修订原因")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("修订原因"), {
      target: { value: "保留纠错草稿" },
    });
    fireEvent.click(screen.getByRole("button", { name: "人工修订与纠错" }));
    expect(screen.queryByRole("textbox", { name: "修订原因" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "人工修订与纠错" }));
    expect(
      (screen.getByLabelText("修订原因") as HTMLTextAreaElement).value,
    ).toBe("保留纠错草稿");
    expect(screen.getByText("此来源尚无代表评论。")).toBeTruthy();
    expect(api.related).toHaveBeenCalledWith(
      { event_id: "event" },
      expect.anything(),
    );
  });

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
    expect(
      screen.getByText(
        (_, node) =>
          node?.tagName === "P" && !!node.textContent?.startsWith("首次发布"),
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        (_, node) =>
          node?.tagName === "SPAN" && node.textContent === "评论：未知",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        (_, node) => node?.tagName === "SPAN" && node.textContent === "点赞：0",
      ),
    ).toBeTruthy();
    expect(screen.getAllByText("该成员证据暂不可读").length).toBeGreaterThan(0);
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
