import { publicationTime } from "@/components/publication/reading-format";

export type EventSource = {
  id: string;
  number: number;
  source: string;
  title: string;
  time: string | null;
  href: string | null;
  originalUrl: string | null;
  availability: "readable" | "unavailable" | "pending";
  metrics?: HotKeyAPI.ContentMetricView;
};

export type TimelineEntry = {
  id: string;
  title: string;
  source: string;
  time: string | null;
  sourceId: string;
  references?: EventSource[];
  reportCount?: number;
};

export type RepresentativeComment = {
  id: string;
  source: string;
  state: "none" | "readable" | "unavailable";
  body: string | null;
  time: string | null;
  originalUrl: string | null;
};

export function safeEventUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    return ["http:", "https:"].includes(new URL(value).protocol) ? value : null;
  } catch {
    return null;
  }
}

export function eventSourceAnchor(id: string) {
  return `event-source-${encodeURIComponent(id)}`;
}

export function eventTime(value: string | null | undefined) {
  if (!value || !Number.isFinite(Date.parse(value))) return "时间未提供";
  return publicationTime(value);
}

export function workbenchSources(
  members: HotKeyAPI.EventMemberReadView[],
  facts: HotKeyAPI.EventFactView[] = [],
): EventSource[] {
  // The ledger includes unloaded fixed references, so every citation has a
  // stable target without replacing evidence with a newer content version.
  const sources = new Map<string, EventSource>();
  for (const fact of facts) {
    for (const member of fact.members) {
      if (sources.has(member.event_member_id)) continue;
      sources.set(member.event_member_id, {
        id: member.event_member_id,
        number: sources.size + 1,
        source: "来源待读取",
        title:
          member.availability === "readable"
            ? "此来源尚未加载"
            : "该成员证据暂不可读",
        time: null,
        href: null,
        originalUrl: null,
        availability:
          member.availability === "readable" ? "pending" : "unavailable",
      });
    }
  }
  for (const member of members) {
    const reading = member.availability === "readable" ? member.content : null;
    const observation = reading?.observation;
    sources.set(member.id, {
      id: member.id,
      number: sources.get(member.id)?.number ?? sources.size + 1,
      source: member.source_key ?? "来源未提供",
      title: reading
        ? (observation?.content_version?.title ?? "成员内容")
        : "该成员证据暂不可读",
      time: observation?.published_at ?? observation?.observed_at ?? null,
      href: reading ? `/content/${reading.id}` : null,
      originalUrl:
        safeEventUrl(observation?.canonical_url) ??
        safeEventUrl(observation?.final_url),
      availability: reading ? "readable" : "unavailable",
      metrics: observation?.metrics,
    });
  }
  return [...sources.values()];
}

export function publicSources(
  items: HotKeyAPI.PublicItemView[],
): EventSource[] {
  return [...new Map(items.map((item) => [item.id, item])).values()].map(
    (item, index) => ({
      id: item.id,
      number: index + 1,
      source: item.source.name,
      title: item.title,
      time: item.timeline_at,
      href: item.reading_url,
      originalUrl: safeEventUrl(item.original_url),
      availability: "readable",
    }),
  );
}

export function sourceTimeline(sources: EventSource[]): TimelineEntry[] {
  return sources
    .filter((source) => source.availability !== "pending")
    .map((source) => ({
      id: source.id,
      title: source.title,
      source: source.source,
      time: source.time,
      sourceId: source.id,
    }))
    .sort((a, b) => {
      const first = a.time ? Date.parse(a.time) : NaN;
      const second = b.time ? Date.parse(b.time) : NaN;
      if (!Number.isFinite(first)) return Number.isFinite(second) ? 1 : 0;
      if (!Number.isFinite(second)) return -1;
      return first - second;
    });
}

export function memberComments(
  members: HotKeyAPI.EventMemberReadView[],
): RepresentativeComment[] {
  const comments = new Map<string, RepresentativeComment>();
  for (const member of members) {
    if (member.availability !== "readable" || !member.content) continue;
    const reading = member.content;
    const comment =
      reading.representative_comment_state === "readable"
        ? reading.representative_comment
        : null;
    const id = comment?.id ?? member.id;
    if (comments.has(id)) continue;
    comments.set(id, {
      id,
      source: reading.source_key,
      state: reading.representative_comment_state,
      body:
        comment?.observation.content_version?.body ??
        comment?.observation.content_version?.title ??
        null,
      time: comment?.observation.observed_at ?? null,
      originalUrl:
        safeEventUrl(comment?.observation.canonical_url) ??
        safeEventUrl(comment?.observation.final_url),
    });
  }
  return [...comments.values()];
}

export function heatHistoryPoints(history: HotKeyAPI.EventAttentionView[]) {
  return [
    ...new Map(
      history
        .filter((row) => Number.isFinite(Date.parse(row.window_end)))
        .map((row) => [row.window_end, row]),
    ).values(),
  ]
    .sort((a, b) => Date.parse(a.window_end) - Date.parse(b.window_end))
    .map((row) => ({
      time: Date.parse(row.window_end),
      heat:
        row.participant_count > 0 && Number.isFinite(row.heat)
          ? row.heat
          : null,
    }));
}
