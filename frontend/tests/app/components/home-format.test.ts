import { expect, it } from "vitest";
import {
  homeOverview,
  relativeTime,
  storyPresentation,
  type HomeReading,
} from "@/app/components/home-format";
import { attention, publicItem, publicStory } from "./home-fixtures";

const reading: HomeReading = {
  items: [publicItem],
  stories: [publicStory],
  topics: [],
  editions: [],
  unavailable: [],
};

it("counts only this returned list, distinguishes failed counts from zero and uses content times", () => {
  expect(homeOverview(reading)).toEqual({
    itemCount: 1,
    storyCount: 1,
    updatedAt: "2026-10-06T07:00:00Z",
  });
  expect(
    homeOverview({ ...reading, items: [], unavailable: ["items"] }).itemCount,
  ).toBeNull();
  expect(
    homeOverview({ ...reading, stories: [], unavailable: ["stories"] })
      .storyCount,
  ).toBeNull();
  expect(
    homeOverview({
      items: [],
      stories: [],
      topics: [],
      editions: [],
      unavailable: [],
      observedAt: "2026-10-06T08:00:00Z",
    }),
  ).toEqual({ itemCount: 0, storyCount: 0, updatedAt: null });
  expect(
    homeOverview({
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
    }).updatedAt,
  ).toBe("2026-10-06T08:00:00Z");
  expect(
    homeOverview({
      ...reading,
      items: [
        { ...publicItem, timeline_at: "invalid", discovered_at: "invalid" },
      ],
      stories: [],
    }).updatedAt,
  ).toBeNull();
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
