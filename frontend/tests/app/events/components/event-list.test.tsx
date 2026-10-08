// @vitest-environment happy-dom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
const notifications = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications }));

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
import { ApiRequestError } from "@/request";

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("confirmed event list", () => {
  it("does not notify when an in-flight read is cancelled", async () => {
    api.topics.mockResolvedValue({ items: [], next_cursor: null });
    api.sources.mockResolvedValue({ items: [], next_cursor: null });
    api.events.mockRejectedValue(
      new ApiRequestError({ kind: "cancelled", message: "cancelled" }),
    );
    render(<EventList />);
    await waitFor(() => expect(api.events).toHaveBeenCalledOnce());
    expect(notifications.error).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "重试事件读取" })).toBeNull();
  });
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
    expect(notifications.error).toHaveBeenCalledWith(
      "事件读取失败，请稍后重试。",
    );
    expect(screen.queryByText("事件读取失败，请稍后重试。")).toBeNull();
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

  it("keeps readable rows and the same pagination cursor after a failed action", async () => {
    api.topics.mockResolvedValue({ items: [], next_cursor: null });
    api.sources.mockResolvedValue({ items: [], next_cursor: null });
    api.events
      .mockResolvedValueOnce({
        items: [
          {
            id: "event-a",
            title: "已读取事件",
            summary: null,
            member_count: 1,
            readable_member_count: 1,
            evidence_state: "complete",
            source_counts: {},
            first_seen_at: "2026-10-02T00:00:00Z",
          },
        ],
        next_cursor: "same-cursor",
      })
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ items: [], next_cursor: null });
    render(<EventList />);
    fireEvent.click(
      await screen.findByRole("button", { name: "加载更多事件" }),
    );
    await waitFor(() => expect(notifications.error).toHaveBeenCalledOnce());
    expect(screen.getByRole("link", { name: "已读取事件" })).toBeTruthy();
    expect(screen.queryByText("事件读取失败，请稍后重试。")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "加载更多事件" }));
    await waitFor(() => expect(api.events).toHaveBeenCalledTimes(3));
    expect(api.events.mock.calls[1][0].cursor).toBe("same-cursor");
    expect(api.events.mock.calls[2][0].cursor).toBe("same-cursor");
  });
});

it.each([401, 403])(
  "removes private event titles when the next page is denied (%s)",
  async (status) => {
    api.topics.mockResolvedValue({ items: [], next_cursor: null });
    api.sources.mockResolvedValue({ items: [], next_cursor: null });
    api.events
      .mockResolvedValueOnce({
        items: [
          {
            id: "event-a",
            title: "私有旧事件",
            summary: "私有旧摘要",
            member_count: 1,
            readable_member_count: 1,
            evidence_state: "complete",
            source_counts: {},
            first_seen_at: "2026-10-02T00:00:00Z",
          },
        ],
        next_cursor: "next",
      })
      .mockRejectedValueOnce(
        new ApiRequestError({
          kind: "http",
          status,
          code: "permission_denied",
          message: "请求被拒绝",
        }),
      );
    render(<EventList />);
    fireEvent.click(
      await screen.findByRole("button", { name: "加载更多事件" }),
    );
    await screen.findByRole("heading", { name: "暂时无法访问事件" });
    expect(screen.queryByText("私有旧事件")).toBeNull();
    expect(screen.queryByText("私有旧摘要")).toBeNull();
    expect(screen.queryByRole("button", { name: "加载更多事件" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  },
);

it.each([401, 403])(
  "shows event permission denial on the initial read (%s)",
  async (status) => {
    api.topics.mockResolvedValue({ items: [], next_cursor: null });
    api.sources.mockResolvedValue({ items: [], next_cursor: null });
    api.events.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status,
        code: "permission_denied",
        message: "请求被拒绝",
      }),
    );
    render(<EventList />);
    await screen.findByRole("heading", { name: "暂时无法访问事件" });
    expect(screen.queryByRole("alert")).toBeNull();
  },
);
