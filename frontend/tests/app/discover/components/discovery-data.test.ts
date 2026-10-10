import { expect, it } from "vitest";
import {
  discoveryFailure,
  discoveryHref,
  discoveryScope,
  discoverySources,
} from "@/app/discover/components/discovery-data";
import { ApiRequestError } from "@/request";
import { publicItem } from "../../components/home-fixtures";

it("normalizes existing scope values without adding unsupported result types", () => {
  expect(
    discoveryScope({
      mode: "selected",
      category: "paper",
      window: "7d",
      by: "published",
      channel: "firstParty",
    }),
  ).toEqual({
    mode: "selected",
    category: "paper",
    window: "7d",
    by: "published",
    channel: "firstParty",
  });
  expect(
    discoveryScope({
      mode: "bad",
      category: "event",
      window: "30d",
      by: "bad",
      channel: "bilibili",
    }),
  ).toEqual({
    mode: "all",
    category: undefined,
    window: "24h",
    by: "timeline",
    channel: undefined,
  });
});

it("keeps every existing query field and safely encodes cursors for first/next page links", () => {
  const params = {
    q: "模型 & 研究",
    category: "paper",
    mode: "selected",
    window: "7d",
    by: "published",
    channel: "news",
    source_key: "rss",
    tag: "中文",
    topic: "research",
    search_order: "time",
    cursor: "old",
    blank: "",
  };
  const next = new URL(
    discoveryHref(params, "signed+/next="),
    "https://hotkey.test",
  );
  for (const [key, value] of Object.entries(params)) {
    if (key !== "cursor" && key !== "blank")
      expect(next.searchParams.get(key)).toBe(value);
  }
  expect(next.searchParams.get("cursor")).toBe("signed+/next=");
  expect(next.searchParams.has("blank")).toBe(false);
  const first = new URL(discoveryHref(params), "https://hotkey.test");
  expect(first.searchParams.has("cursor")).toBe(false);
  expect(first.searchParams.get("q")).toBe(params.q);
});

it("uses only configured source names, including paused sources, without adding item sources", () => {
  expect(
    discoverySources({
      items: [publicItem, publicItem],
      source_status: [
        {
          source_key: "offline",
          name: "暂停来源",
          enabled: false,
          health: "failing",
          last_success_at: null,
        },
        {
          source_key: "rss",
          name: "较旧的名称",
          enabled: true,
          health: "ok",
          last_success_at: null,
        },
      ],
      next_cursor: null,
      snapshot_at: "2026-10-06T08:00:00Z",
    }),
  ).toEqual([
    { key: "offline", name: "暂停来源" },
    { key: "rss", name: "较旧的名称" },
  ]);
  expect(
    discoverySources({
      items: [publicItem],
      next_cursor: null,
      snapshot_at: "2026-10-06T08:00:00Z",
    }),
  ).toEqual([]);
  expect(discoverySources(null)).toEqual([]);
});

it("uses code/status branches and strips internal error text", () => {
  const known = discoveryFailure(
    new ApiRequestError({
      kind: "http",
      code: "publication_search_busy",
      status: 503,
      message: "private detail",
    }),
  );
  expect(known.code).toBe("publication_search_busy");
  expect(known.status).toBe(503);
  expect(known.message).not.toContain("private detail");
  expect(discoveryFailure(new Error("private detail")).code).toBe(
    "publication_read_failed",
  );
  expect(
    discoveryFailure(
      new ApiRequestError({ kind: "network", message: "private detail" }),
    ).code,
  ).toBe("network");
});
