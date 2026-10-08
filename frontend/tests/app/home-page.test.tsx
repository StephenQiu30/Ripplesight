import { type ReactElement } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { HomeReading } from "@/app/components/home-format";
import { publicStory } from "./components/home-fixtures";
import { ApiRequestError } from "@/request";
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
beforeEach(() => {
  vi.clearAllMocks();
  api.hot.mockResolvedValue({ stories: [publicStory] });
  api.editions.mockResolvedValue({ entries: [] });
});
async function read(params: Record<string, string> = {}) {
  const shell = await Home({ searchParams: Promise.resolve(params) });
  const boundary = shell.props.children as ReactElement<
    Record<string, unknown>
  >;
  return await (
    boundary.type as (
      props: typeof boundary.props,
    ) => Promise<ReactElement<{ reading: HomeReading; category?: string }>>
  )(boundary.props);
}
it("loads the event design without fetching the retired article feed or topic sidebar", async () => {
  const page = await read();
  expect(api.hot).toHaveBeenCalledWith({ limit: 50 });
  expect(api.editions).toHaveBeenCalledWith({ kind: "daily", limit: 1 });
  expect(api.items).not.toHaveBeenCalled();
  expect(api.topics).not.toHaveBeenCalled();
  expect(page.props.reading.stories).toEqual([publicStory]);
});
it("normalizes unsupported categories while accepting the design's categories", async () => {
  expect((await read({ category: "bad" })).props.category).toBeUndefined();
  expect((await read({ category: "policy" })).props.category).toBe("policy");
});
it("isolates a failed daily edition and never serializes provider messages", async () => {
  api.editions.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status: 503,
      code: "database_unavailable",
      message: "private provider details",
    }),
  );
  const { reading } = (await read()).props;
  expect(reading.stories).toEqual([publicStory]);
  expect(reading.unavailable).toEqual(["editions"]);
  expect(reading.failures).toEqual({
    editions: { status: 503, code: "database_unavailable" },
  });
  expect(JSON.stringify(reading)).not.toContain("private provider");
});
it.each(["hot", "editions"] as const)(
  "treats unpublished %s as empty without fake records",
  async (key) => {
    api[key].mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        status: 404,
        code: "publication_not_configured",
        message: "unpublished",
      }),
    );
    const { reading } = (await read()).props;
    expect(reading.unavailable).toEqual([]);
    expect(key === "hot" ? reading.stories : reading.editions).toEqual([]);
  },
);
