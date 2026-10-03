import { selectOption } from "../../../../select";
// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const notifications = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications }));

const api = vi.hoisted(() => ({
  correct: vi.fn(),
  events: vi.fn(),
  push: vi.fn(),
}));
vi.mock("@/api/shijian", () => ({
  correctEvent: api.correct,
  listEvents: api.events,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push }) }));

import { EventCorrections } from "@/app/events/[eventId]/components/event-corrections";
import { ApiRequestError } from "@/request";

const event: HotKeyAPI.EventReadView = {
  id: "event",
  topic_id: "topic",
  revision: 3,
  title: "事件",
  summary: "摘要",
  first_seen_at: "2026-10-02T00:00:00Z",
  first_seen_basis: "published",
  status: "active",
  merged_into_id: null,
  evidence_state: "complete",
  derived_text_available: true,
  member_count: 1,
  readable_member_count: 1,
  source_counts: { x: 1 },
  created_at: "2026-10-02T00:00:00Z",
  updated_at: "2026-10-02T00:00:00Z",
};

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
beforeEach(() =>
  api.events.mockResolvedValue({ items: [], next_cursor: null }),
);

describe("manual event correction", () => {
  it("reuses the operation id for an explicit network retry and sends fixed revisions plus CSRF", async () => {
    const changed = vi.fn();
    api.correct
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValue({ target_event_id: "new-event" });
    render(
      <EventCorrections
        event={event}
        selectedContentIds={["content"]}
        selectedFactIds={[]}
        facts={[]}
        onChanged={changed}
      />,
    );
    fireEvent.change(screen.getByLabelText("修订原因"), {
      target: { value: "独立事实" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交人工修订" }));
    await waitFor(() =>
      expect(notifications.error).toHaveBeenCalledWith(
        "修订提交失败。重试将复用本次操作编号。",
      ),
    );
    expect(
      screen.queryByText("修订提交失败。重试将复用本次操作编号。"),
    ).toBeNull();
    const operationId = api.correct.mock.calls[0][0].operation_id;
    fireEvent.click(screen.getByRole("button", { name: "提交人工修订" }));
    await waitFor(() => expect(changed).toHaveBeenCalledOnce());
    expect(api.correct).toHaveBeenLastCalledWith(
      expect.objectContaining({
        kind: "split",
        operation_id: operationId,
        content_ids: ["content"],
        expected_revisions: { event: 3 },
      }),
      { headers: { "X-HotKey-CSRF": "1" } },
    );
    expect(api.push).toHaveBeenCalledWith("/events/new-event");
  });

  it("merges against the current target revision and exposes conflicts without automatic retries", async () => {
    api.events.mockResolvedValue({
      items: [{ ...event, id: "target", revision: 7, title: "目标事件" }],
      next_cursor: null,
    });
    api.correct.mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        code: "event_revision_conflict",
        status: 409,
        message: "修订冲突",
      }),
    );
    render(
      <EventCorrections
        event={event}
        selectedContentIds={[]}
        selectedFactIds={[]}
        facts={[]}
        onChanged={vi.fn()}
      />,
    );
    await selectOption(
      screen.getByLabelText("修订操作"),
      "将整个事件合并到其他事件",
    );
    await screen.findByLabelText("目标事件");
    await selectOption(screen.getByLabelText("目标事件"), "目标事件 · 修订 7");
    fireEvent.change(screen.getByLabelText("修订原因"), {
      target: { value: "同故事" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交人工修订" }));
    await waitFor(() =>
      expect(notifications.error).toHaveBeenCalledWith(
        "事件修订已变化。刷新详情并重新选择后再提交。",
      ),
    );
    expect(
      screen.queryByText("事件修订已变化。刷新详情并重新选择后再提交。"),
    ).toBeNull();
    expect(api.correct).toHaveBeenCalledOnce();
    expect(api.correct.mock.calls[0][0]).toMatchObject({
      kind: "merge",
      target_event_id: "target",
      expected_revisions: { event: 3, target: 7 },
    });
    expect(api.correct.mock.calls[0][0].content_ids).toBeUndefined();
  });
});
