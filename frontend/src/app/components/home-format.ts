export type HomeReading = {
  items: HotKeyAPI.PublicItemView[];
  stories: HotKeyAPI.PublicStoryView[];
  topics: HotKeyAPI.PublicTopicSummaryView[];
  editions: HotKeyAPI.PublicEditionIndexView[];
  unavailable: string[];
  failures?: Record<string, { code?: string; status?: number }>;
  sourceStatus?: HotKeyAPI.PublicSourceStatusView[];
  nextCursor?: string | null;
  observedAt?: string;
};

export function latestTime(values: (string | null | undefined)[]) {
  const dates = values.filter(
    (value): value is string =>
      Boolean(value) && Number.isFinite(Date.parse(value!)),
  );
  return dates.sort((a, b) => Date.parse(b) - Date.parse(a))[0] ?? null;
}

export function homeOverview(reading: HomeReading) {
  return {
    itemCount: reading.unavailable.includes("items")
      ? null
      : reading.items.length,
    storyCount: reading.unavailable.includes("stories")
      ? null
      : reading.stories.length,
    updatedAt: latestTime([
      ...reading.items.flatMap((item) => [
        item.discovered_at,
        item.timeline_at,
      ]),
      ...reading.stories.flatMap((story) => [
        story.first_seen_at,
        story.attention?.last_source_time,
        ...story.reports.flatMap((item) => [
          item.discovered_at,
          item.timeline_at,
        ]),
      ]),
      ...reading.topics.map((topic) => topic.latest_at),
      ...reading.editions.map((edition) => edition.created_at),
    ]),
  };
}

const trendLabels = {
  new: "首次出现",
  up: "上升",
  down: "下降",
  flat: "持平",
  unknown: "变化未知",
} as const;
export const storyBadgeLabels = {
  new: "首次出现",
  surge: "来源骤增",
  rising: "持续升温",
} as const;

export function storyPresentation(story: HotKeyAPI.PublicStoryView) {
  const sources = [
    ...new Map(
      story.reports.map((item) => [item.source.key, item.source.name]),
    ).values(),
  ];
  const attention = story.attention;
  const heat = attention?.heat ?? story.heat;
  return {
    sources,
    sourceCount: attention?.participant_count ?? sources.length,
    sourceCountLabel: attention ? "个独立来源" : "个已列来源",
    heat: heat != null && Number.isFinite(heat) ? heat : null,
    // The API compares the same participants. Raw total heat can change solely
    // because coverage changed, so it must not override an unknown/new trend.
    trend: attention?.trend ?? "unknown",
    trendLabel: trendLabels[attention?.trend ?? "unknown"],
    badges: attention?.badges ?? [],
    categories: [
      ...new Set(
        story.reports
          .map((item) => item.category)
          .filter((category) => category !== null),
      ),
    ],
    time: latestTime([
      attention?.last_source_time,
      ...story.reports.map((item) => item.timeline_at),
      story.first_seen_at,
    ]),
  };
}

export function relativeTime(value: string | null, observedAt: string) {
  if (!value || !Number.isFinite(Date.parse(value))) return "时间未知";
  const seconds = Math.floor(
    (Date.parse(observedAt) - Date.parse(value)) / 1000,
  );
  if (!Number.isFinite(seconds) || seconds < 0) return "时间待核对";
  if (seconds < 60) return "刚刚";
  const formatter = new Intl.RelativeTimeFormat("zh-CN", { numeric: "always" });
  if (seconds < 3600)
    return formatter.format(-Math.floor(seconds / 60), "minute");
  if (seconds < 86400)
    return formatter.format(-Math.floor(seconds / 3600), "hour");
  return formatter.format(-Math.floor(seconds / 86400), "day");
}
