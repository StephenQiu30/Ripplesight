export const homeCategories = [
  ["all", "全部"],
  ["ai-models", "模型发布"],
  ["ai-products", "产品"],
  ["paper", "研究"],
  ["open-source", "开源"],
  ["policy", "政策与安全"],
] as const;
export type HomeReading = {
  stories: HotKeyAPI.PublicStoryView[];
  editions: HotKeyAPI.PublicEditionIndexView[];
  unavailable: string[];
  failures?: Record<string, { code?: string; status?: number }>;
  observedAt?: string;
  windowStart?: string;
  overview?: HotKeyAPI.PublicHomeOverview;
  sentiment?: HotKeyAPI.PublicReportSentimentView | null;
  negativeSurge?: HotKeyAPI.PublicNegativeSurgeView | null;
  platformTrends?: HotKeyAPI.PublicPlatformTrend[];
  rankingBasis?: HotKeyAPI.PublicHomeView["ranking_basis"];
};

export function latestTime(values: (string | null | undefined)[]) {
  const dates = values.filter(
    (value): value is string =>
      Boolean(value) && Number.isFinite(Date.parse(value!)),
  );
  return dates.sort((a, b) => Date.parse(b) - Date.parse(a))[0] ?? null;
}

export function homeUpdatedAt(reading: HomeReading) {
  reading = readableHomeReading(reading);
  return latestTime([
    ...reading.stories.flatMap((story) => [
      story.first_seen_at,
      story.attention?.last_source_time,
      ...story.reports.flatMap((item) => [
        item.discovered_at,
        item.timeline_at,
      ]),
    ]),
    ...reading.editions.map((edition) => edition.created_at),
  ]);
}

/** A failed section must not leak old content through derived UI either. */
export function readableHomeReading(reading: HomeReading): HomeReading {
  return {
    ...reading,
    platformTrends:
      reading.unavailable.includes("stories") || reading.failures?.stories
        ? undefined
        : reading.platformTrends,
    negativeSurge:
      reading.unavailable.includes("stories") || reading.failures?.stories
        ? undefined
        : reading.negativeSurge,
    sentiment:
      reading.unavailable.includes("stories") || reading.failures?.stories
        ? undefined
        : reading.sentiment,
    overview:
      reading.unavailable.includes("stories") || reading.failures?.stories
        ? undefined
        : reading.overview,
    stories:
      reading.unavailable.includes("stories") || reading.failures?.stories
        ? []
        : reading.stories,
    editions:
      reading.unavailable.includes("editions") || reading.failures?.editions
        ? []
        : reading.editions,
  };
}

/** Material discovery is distinct from event occurrence and fact confirmation. */
export function storyObservation(
  story: HotKeyAPI.PublicStoryView,
  observedAt: string,
) {
  const reference = Date.parse(observedAt);
  const validReference = Number.isFinite(reference);
  const discoveries = story.reports.map((item) => item.discovered_at);
  const discoveryTimes = discoveries.filter(
    (value) =>
      Number.isFinite(Date.parse(value)) &&
      (!validReference || Date.parse(value) <= reference),
  );
  return {
    discoveredAt: latestTime(discoveryTimes),
    materialAt: latestTime(story.reports.map((item) => item.timeline_at)),
    recentMaterials:
      validReference &&
      discoveryTimes.some(
        (value) => Date.parse(value) > reference - 24 * 60 * 60 * 1000,
      ),
    unverifiedDiscovery: discoveries.some(
      (value) =>
        !Number.isFinite(Date.parse(value)) ||
        (validReference && Date.parse(value) > reference),
    ),
    backfill: story.reports.some((item) => item.backfill),
  };
}

export function homeRisingStories(stories: HotKeyAPI.PublicStoryView[]) {
  return stories
    .filter(
      (story) =>
        story.history?.trend.state === "available" &&
        story.history.trend.direction === "up" &&
        story.history.trend.percent != null &&
        Number.isFinite(story.history.trend.percent) &&
        story.history.trend.percent > 0,
    )
    .sort((a, b) => b.history!.trend.percent! - a.history!.trend.percent!)
    .slice(0, 5);
}

export function homeMonitorHref(title: string) {
  // The existing form accepts at most 200 UTF-16 code units. Do not split a
  // surrogate pair when shortening a title before URI encoding.
  let keywords = "";
  for (const character of title.trim()) {
    if (keywords.length + character.length > 200) break;
    keywords += character;
  }
  return `/monitors/new?${new URLSearchParams({ q: keywords })}`;
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
