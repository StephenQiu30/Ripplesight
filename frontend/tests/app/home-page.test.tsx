import { type ReactElement } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { type HomeReading } from "@/app/components/home-format";
import { publicItem, publicStory } from "./components/home-fixtures";

const api = vi.hoisted(() => ({
  items: vi.fn(),
  hot: vi.fn(),
  topics: vi.fn(),
  editions: vi.fn(),
  connection: vi.fn(),
}));
vi.mock("next/server", () => ({ connection: api.connection }));
vi.mock("@/api/gongkaifabu", () => ({
  listPublicItems: api.items,
  getPublicHotStories: api.hot,
  getPublicTopicDirectory: api.topics,
}));
vi.mock("@/api/gongkaikanwumulu", () => ({
  listPublicEditionCatalogue: api.editions,
}));
import Home from "@/app/page";
import { ApiRequestError } from "@/request";

beforeEach(() => {
  vi.clearAllMocks();
  api.items.mockResolvedValue({
    items: [publicItem],
    source_status: [],
    next_cursor: "next",
    snapshot_at: "2026-10-06T08:00:00Z",
  });
  api.hot.mockResolvedValue({ stories: [publicStory], ranking_basis: "heat" });
  api.topics.mockResolvedValue({ topics: [], refresh_at: null });
  api.editions.mockResolvedValue({ entries: [] });
});
afterEach(() => vi.useRealTimers());

async function readHome(
  params: { mode?: string; category?: string; cursor?: string } = {},
) {
  const shell = await Home({ searchParams: Promise.resolve(params) });
  const boundary = shell.props.children as ReactElement<{
    mode: "all" | "selected";
    category?: HotKeyAPI.PublicItemView["category"];
    cursor?: string;
  }>;
  const render = boundary.type as (props: typeof boundary.props) => Promise<
    ReactElement<{
      reading: HomeReading;
      mode: string;
      category?: string;
      cursor?: string;
    }>
  >;
  return { shell, content: await render(boundary.props) };
}

it("keeps the homepage anonymous and passes URL scope into only the existing endpoints", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-06T08:00:00Z"));
  const { shell, content } = await readHome({
    mode: "selected",
    category: "paper",
    cursor: "signed-cursor",
  });
  expect(shell.props.fallback.type.name).toBe("HomeLoading");
  expect(api.connection).toHaveBeenCalledTimes(1);
  expect(api.items).toHaveBeenCalledWith({
    mode: "selected",
    category: "paper",
    cursor: "signed-cursor",
    window: "7d",
    limit: 20,
  });
  expect(api.hot).toHaveBeenCalledWith({ limit: 4 });
  expect(api.topics).toHaveBeenCalledTimes(1);
  expect(api.editions).toHaveBeenCalledWith({ limit: 2 });
  expect(content.props).toMatchObject({
    mode: "selected",
    category: "paper",
    cursor: "signed-cursor",
    reading: {
      items: [publicItem],
      stories: [publicStory],
      nextCursor: "next",
      unavailable: [],
      observedAt: "2026-10-06T08:00:00.000Z",
    },
  });
});

it("normalizes unknown scope without losing a valid cursor", async () => {
  await readHome({
    mode: "unknown",
    category: "not-a-category",
    cursor: "page-2",
  });
  expect(api.items).toHaveBeenCalledWith({
    mode: "all",
    category: undefined,
    cursor: "page-2",
    window: "7d",
    limit: 20,
  });
});

it("isolates a topic failure and transports only safe code/status details", async () => {
  api.topics.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      code: "publication_search_busy",
      status: 503,
      message: "Internal details must not be exposed",
    }),
  );
  const { content } = await readHome();
  expect(content.props.reading.unavailable).toEqual(["topics"]);
  expect(content.props.reading.failures).toEqual({
    topics: { code: "publication_search_busy", status: 503 },
  });
  expect(content.props.reading.items).toEqual([publicItem]);
  expect(content.props.reading.stories).toEqual([publicStory]);
  expect(content.props.reading.topics).toEqual([]);
});

it.each(["items", "hot", "topics", "editions"] as const)(
  "treats publication_not_configured from %s as unpublished while preserving other blocks",
  async (section) => {
    api[section].mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        code: "publication_not_configured",
        status: 503,
        message: "Not configured",
      }),
    );
    const { content } = await readHome();
    expect(content.props.reading.unavailable).toEqual([]);
    expect(content.props.reading.failures).toEqual({});
    if (section !== "items")
      expect(content.props.reading.items).toEqual([publicItem]);
    if (section !== "hot")
      expect(content.props.reading.stories).toEqual([publicStory]);
  },
);

it("keeps all failures in their own blocks rather than throwing away the public page", async () => {
  for (const section of [api.items, api.hot, api.topics, api.editions])
    section.mockRejectedValue(new Error("Connection unavailable"));
  const { content } = await readHome();
  expect(content.props.reading.unavailable).toEqual([
    "items",
    "stories",
    "topics",
    "editions",
  ]);
  expect(content.props.reading.items).toEqual([]);
  expect(content.props.reading.stories).toEqual([]);
  expect(content.props.reading.topics).toEqual([]);
  expect(content.props.reading.editions).toEqual([]);
  expect(content.props.reading.nextCursor).toBeNull();
});
