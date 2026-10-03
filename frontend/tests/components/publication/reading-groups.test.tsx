// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const notifications = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications }));
import { ApiRequestError } from "@/request";
import { GroupExpansion } from "@/components/publication/reading-groups";

const api = vi.hoisted(() => ({ reports: vi.fn(), developments: vi.fn() }));
vi.mock("@/api/gongkaifabu", () => ({
  getPublicFactReports: api.reports,
  getPublicStoryDevelopments: api.developments,
}));
vi.mock("@/components/publication/reading-parts", () => ({
  publicationTime: (value: string) => value,
  PublicItemCards: ({ items }: { items: HotKeyAPI.PublicItemView[] }) => (
    <ul>
      {items.map((item) => (
        <li key={item.id}>{item.title}</li>
      ))}
    </ul>
  ),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
const item: HotKeyAPI.PublicItemView = {
  id: "00000000-0000-4000-8000-000000000001",
  revision: 1,
  title: "固定许可报道",
  original_title: null,
  summary: "公开摘要",
  source: {
    key: "controlled",
    name: "受控来源",
    kind: "rss",
    first_party: true,
  },
  original_url: "https://source.example/item",
  reading_url: "/discover/items/00000000-0000-4000-8000-000000000001",
  published_at: null,
  discovered_at: "2026-10-02T00:00:00Z",
  timeline_at: "2026-10-02T00:00:00Z",
  category: "industry",
  tags: ["OpenAI"],
  score: 85,
  selected: true,
  reason: null,
  event_id: "event",
  fact_id: "fact",
  indexable: false,
};
const filters: HotKeyAPI.PublicReadingFilters = {
  window: "7d",
  channel: "firstParty",
  category: "industry",
  source_key: "controlled",
  tag: "OpenAI",
  topic: "openai",
};

it("binds expansion to the same filters and revision, and clears old reports after a 409", async () => {
  api.reports.mockResolvedValueOnce({
    reports: [item],
    revision: "r1",
    next_cursor: "page2",
  });
  api.reports.mockRejectedValueOnce(
    new ApiRequestError({
      kind: "http",
      status: 409,
      code: "publication_cursor_stale",
      message: "changed",
    }),
  );
  api.reports.mockResolvedValueOnce({
    reports: [{ ...item, title: "重读后的许可报道" }],
    revision: "r2",
    next_cursor: null,
  });
  render(
    <GroupExpansion
      group={{ fact_id: "fact", event_id: "event" }}
      filters={filters}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "展开同事实报道" }));
  await screen.findByText("固定许可报道");
  fireEvent.click(screen.getByRole("button", { name: "加载更多" }));
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith(
      "报道或许可已经变化，请重新展开。",
    ),
  );
  expect(screen.queryByText("报道或许可已经变化，请重新展开。")).toBeNull();
  expect(screen.queryByText("固定许可报道")).toBeNull();
  expect(api.reports).toHaveBeenNthCalledWith(2, {
    ...filters,
    fact_id: "fact",
    limit: 20,
    cursor: "page2",
    revision: "r1",
  });
  fireEvent.click(screen.getByRole("button", { name: "重新展开" }));
  await screen.findByText("重读后的许可报道");
  expect(api.reports).toHaveBeenNthCalledWith(3, {
    ...filters,
    fact_id: "fact",
    limit: 20,
    cursor: undefined,
    revision: undefined,
  });
});

it("does not invent a development count and sends the actual event with inherited filters", async () => {
  api.developments.mockResolvedValue({
    developments: [
      {
        fact_id: "fact2",
        anchor_at: item.timeline_at,
        report_count: 2,
        representative: item,
      },
    ],
    revision: "d1",
    next_cursor: null,
  });
  render(
    <GroupExpansion
      group={{ fact_id: "fact", event_id: "event" }}
      filters={filters}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "展开事实与进展" }));
  await screen.findByText("固定许可报道");
  expect(api.developments).toHaveBeenCalledWith({
    ...filters,
    event_id: "event",
    limit: 20,
    cursor: undefined,
    revision: undefined,
  });
  expect(screen.getByText(/2 篇公开报道/)).toBeTruthy();
});
