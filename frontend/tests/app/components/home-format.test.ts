import { expect, it } from "vitest";
import {
  homeUpdatedAt,
  relativeTime,
  storyPresentation,
  storyObservation,
  homeMonitorHref,
  homeRisingStories,
  type HomeReading,
} from "@/app/components/home-format";
import { attention, publicStory, publicItem } from "./home-fixtures";

const reading: HomeReading = {
  stories: [publicStory],
  editions: [],
  unavailable: [],
};

it("uses published content time rather than request time, and keeps missing timestamps unknown", () => {
  expect(homeUpdatedAt(reading)).toBe("2026-10-06T07:00:00Z");
  expect(
    homeUpdatedAt({
      ...reading,
      stories: [],
      observedAt: "2026-10-06T08:00:00Z",
    }),
  ).toBeNull();
  expect(
    homeUpdatedAt({
      ...reading,
      stories: [
        {
          ...publicStory,
          first_seen_at: "invalid",
          reports: [],
          attention: null,
        },
      ],
    }),
  ).toBeNull();
  expect(
    homeUpdatedAt({
      ...reading,
      editions: [
        {
          kind: "daily",
          key: "2026-10-06",
          title: "日报",
          revision: 1,
          created_at: "2026-10-06T08:00:00Z",
          reading_url: "/reports/daily/2026-10-06",
        },
      ],
    }),
  ).toBe("2026-10-06T08:00:00Z");
});

it.each(["up", "down", "flat", "new", "unknown"] as const)(
  "preserves the API's %s trend even if total heat suggests another direction",
  (trend) => {
    const view = storyPresentation({
      ...publicStory,
      attention: { ...attention, heat: 10, previous_heat: 1000, trend },
    });
    expect(view.trend).toBe(trend);
    expect(view.heat).toBe(10);
    expect(view.trendLabel).toBe(
      {
        up: "上升",
        down: "下降",
        flat: "持平",
        new: "首次出现",
        unknown: "变化未知",
      }[trend],
    );
  },
);

it("uses independent source counts, deduplicates visible sources and keeps unmeasured heat unknown", () => {
  expect(storyPresentation(publicStory)).toMatchObject({
    sources: ["公开来源"],
    sourceCount: 3,
    sourceCountLabel: "个独立来源",
    categories: ["paper"],
    badges: ["surge", "rising"],
  });
  expect(
    storyPresentation({ ...publicStory, attention: null, heat: null }),
  ).toMatchObject({
    sourceCount: 1,
    sourceCountLabel: "个已列来源",
    heat: null,
    trend: "unknown",
    badges: [],
  });
  expect(
    storyPresentation({ ...publicStory, attention: null, heat: 0 }).heat,
  ).toBe(0);
  expect(
    storyPresentation({ ...publicStory, attention: null, heat: NaN }).heat,
  ).toBeNull();
});

it("formats relative times against a stable server observation without presenting future timestamps as fresh", () => {
  const now = "2026-10-06T08:00:00Z";
  expect(relativeTime("2026-10-06T07:00:00Z", now)).toBe("1小时前");
  expect(relativeTime("2026-10-06T07:59:10Z", now)).toBe("刚刚");
  expect(relativeTime("2026-10-06T07:55:00Z", now)).toBe("5分钟前");
  expect(relativeTime("2026-10-04T08:00:00Z", now)).toBe("2天前");
  expect(relativeTime(null, now)).toBe("时间未知");
  expect(relativeTime("invalid", now)).toBe("时间未知");
  expect(relativeTime("2026-10-07T08:00:00Z", now)).toBe("时间待核对");
});

it.each([
  ["2026-10-05T08:00:00Z", false],
  ["2026-10-05T08:00:01Z", true],
  ["2026-10-06T08:00:00Z", true],
  ["2026-10-06T08:00:01Z", false],
  ["invalid", false],
])(
  "uses only material discovery within the rolling 24h window: %s",
  (time, recent) => {
    const observation = storyObservation(
      {
        ...publicStory,
        // A newly dated event reference does not make old materials new.
        first_seen_at: "2026-10-06T08:00:00Z",
        reports: [{ ...publicItem, discovered_at: time }],
      },
      "2026-10-06T08:00:00Z",
    );
    expect(observation.recentMaterials).toBe(recent);
  },
);

it("preserves valid discoveries and flags future/invalid records and backfills separately", () => {
  const observation = storyObservation(
    {
      ...publicStory,
      reports: [
        publicItem,
        { ...publicItem, discovered_at: "2026-10-07T08:00:00Z" },
        { ...publicItem, discovered_at: "invalid" },
      ],
    },
    "2026-10-06T08:00:00Z",
  );
  expect(observation).toMatchObject({
    discoveredAt: publicItem.discovered_at,
    recentMaterials: true,
    unverifiedDiscovery: true,
    backfill: true,
  });
  expect(storyObservation(publicStory, "invalid").recentMaterials).toBe(false);
  expect(storyObservation({ ...publicStory, reports: [] }, "")).toMatchObject({
    discoveredAt: null,
    materialAt: null,
    recentMaterials: false,
  });
});

it("ranks only backend comparable history and never estimates trend from current attention", () => {
  const base: HotKeyAPI.PublicHeatHistory = {
    state: "available",
    event_revision: 1,
    snapshot_at: "2026-10-06T08:00:00Z",
    points: [],
    trend: { state: "available", direction: "up", percent: 20 },
  };
  const rising = { ...publicStory, history: base };
  const fastest = {
    ...rising,
    id: "fastest",
    history: { ...base, trend: { ...base.trend, percent: 50 } },
  };
  const rejected = [
    { state: "insufficient_data" as const },
    { state: "unavailable" as const },
    { direction: "down" as const },
    { percent: NaN },
    { percent: Infinity },
    { percent: 0 },
  ].map((patch, i) => ({
    ...rising,
    id: `rejected-${i}`,
    history: { ...base, trend: { ...base.trend, ...patch } },
  }));
  expect(
    homeRisingStories([publicStory, ...rejected, rising, fastest]),
  ).toEqual([fastest, rising]);
});

it("removes failed sections from the derived header update time", () => {
  const edition = {
    kind: "daily" as const,
    key: "2026-10-01",
    title: "旧刊期",
    revision: 1,
    created_at: "2026-10-06T08:00:00Z",
    reading_url: "/reports/daily/2026-10-01",
  };
  expect(
    homeUpdatedAt({
      ...reading,
      editions: [edition],
      unavailable: ["editions"],
    }),
  ).toBe("2026-10-06T07:00:00Z");
  expect(
    homeUpdatedAt({
      ...reading,
      editions: [edition],
      failures: { stories: { status: 403 }, editions: { status: 503 } },
    }),
  ).toBeNull();
});

it("encodes editable monitor intent with a Unicode-safe 200-unit limit and no execution flags", () => {
  const title = "模型 / 开源? & # + 🧠";
  const url = new URL(homeMonitorHref(title), "http://localhost");
  expect(url.pathname).toBe("/monitors/new");
  expect([...url.searchParams]).toEqual([["q", title]]);
  const longTitle = "文".repeat(199) + "🧠后续";
  expect(new URL(homeMonitorHref(longTitle), url).searchParams.get("q")).toBe(
    "文".repeat(199),
  );
});
