// @vitest-environment happy-dom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  events: vi.fn(),
  topics: vi.fn(),
  sources: vi.fn(),
}));
vi.mock("@/api/shijian", () => ({ listEvents: api.events }));
vi.mock("@/app/events/components/event-hot-list", () => ({
  EventHotList: () => null,
}));
vi.mock("@/api/jiankongzhuti", () => ({ listMonitorTopics: api.topics }));
vi.mock("@/api/laiyuannengli", () => ({ listSourceCapabilities: api.sources }));

import { EventList } from "@/app/events/components/event-list";

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("confirmed event list", () => {
  it("reads real event results, applies search and keeps an unavailable title explicit", async () => {
    api.topics.mockResolvedValue({ items: [], next_cursor: null });
    api.sources.mockResolvedValue({ items: [], next_cursor: null });
    api.events.mockResolvedValue({
      items: [
        {
          id: "event-a",
          title: null,
          summary: null,
          member_count: 2,
          readable_member_count: 1,
          evidence_state: "partial",
          source_counts: { hackernews: 1 },
          first_seen_at: "2026-10-02T00:00:00Z",
        },
      ],
      next_cursor: null,
    });
    render(<EventList />);
    expect(
      await screen.findByRole("link", { name: "证据暂不可读的事件" }),
    ).toBeTruthy();
    expect(screen.getByText("1 / 2 条成员可读")).toBeTruthy();
    expect(api.topics).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 50 }),
      expect.anything(),
    );
    fireEvent.change(screen.getByLabelText("搜索事件"), {
      target: { value: "Acme" },
    });
    fireEvent.click(screen.getByRole("button", { name: "应用筛选" }));
    await waitFor(() =>
      expect(api.events).toHaveBeenLastCalledWith(
        expect.objectContaining({ query: "Acme" }),
        expect.anything(),
      ),
    );
  });

  it("shows an error with retry and loads the next confirmed page", async () => {
    api.topics.mockResolvedValue({ items: [], next_cursor: null });
    api.sources.mockResolvedValue({ items: [], next_cursor: null });
    api.events
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ items: [], next_cursor: "next-page" })
      .mockResolvedValueOnce({ items: [], next_cursor: null });
    render(<EventList />);
    fireEvent.click(
      await screen.findByRole("button", { name: "重试事件读取" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "加载更多事件" }),
    );
    await waitFor(() =>
      expect(api.events).toHaveBeenLastCalledWith(
        expect.objectContaining({ cursor: "next-page" }),
        expect.anything(),
      ),
    );
  });
});
