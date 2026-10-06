import { describe, expect, it } from "vitest";
import {
  eventSourceAnchor,
  eventTime,
  heatHistoryPoints,
  memberComments,
  publicSources,
  safeEventUrl,
  sourceTimeline,
  workbenchSources,
} from "@/components/events/reading-model";
import { fact, heat, member, publicItem } from "./fixtures";

describe("event evidence mapping", () => {
  it("keeps citation targets and numbers for unloaded evidence and fills only the fixed member", () => {
    const references = [
      fact("f1", "later"),
      fact("f2", "loaded"),
      fact("f3", "later"),
    ];
    const pending = workbenchSources([], references);
    expect(
      pending.map((source) => [source.id, source.number, source.availability]),
    ).toEqual([
      ["later", 1, "pending"],
      ["loaded", 2, "pending"],
    ]);
    const loaded = workbenchSources(
      [member("loaded"), member("later")],
      references,
    );
    expect(loaded.map((source) => [source.id, source.number])).toEqual([
      ["later", 1],
      ["loaded", 2],
    ]);
    expect(loaded[0].href).toBe("/content/content-later");
    expect(loaded[0].title).toBe("固定标题 later");
    expect(eventSourceAnchor("member / 1")).toBe(
      "event-source-member%20%2F%201",
    );
  });

  it("does not expose content or metrics on an unavailable fixed member", () => {
    const unavailable = { ...member(), availability: "unavailable" as const };
    const source = workbenchSources([unavailable])[0];
    expect(source.availability).toBe("unavailable");
    expect(source.href).toBeNull();
    expect(source.originalUrl).toBeNull();
    expect(source.metrics).toBeUndefined();
    expect(source.title).toBe("该成员证据暂不可读");
    expect(memberComments([unavailable])).toEqual([]);
  });

  it("deduplicates public reports and sorts the timeline by source time, keeping unknown time last", () => {
    const early = publicItem("early");
    const late = { ...publicItem("late"), timeline_at: "2026-10-03T00:00:00Z" };
    const sources = publicSources([late, early, late]);
    expect(sources).toHaveLength(2);
    expect(
      sourceTimeline([
        ...sources,
        { ...sources[0], id: "unknown", time: null },
      ]).map((entry) => entry.id),
    ).toEqual(["early", "late", "unknown"]);
    expect(eventTime("invalid")).toBe("时间未提供");
    expect(eventTime(null)).toBe("时间未提供");
    expect(eventTime("2026-10-01T16:00:00Z")).toBe("2026年10月2日 00:00");
  });

  it.each([
    "javascript:alert(1)",
    "data:text/html,unsafe",
    "/relative",
    "invalid",
  ])("rejects unsafe original URL %s", (url) => {
    expect(safeEventUrl(url)).toBeNull();
  });
  it("keeps HTTP and HTTPS originals", () => {
    expect(safeEventUrl("https://source.example/item")).toBe(
      "https://source.example/item",
    );
    expect(safeEventUrl("http://source.example/item")).toBe(
      "http://source.example/item",
    );
  });

  it("separates none and unavailable and deduplicates latest readable comments without inventing sentiment", () => {
    const none = member("none");
    const unavailable = member("unavailable");
    unavailable.content!.representative_comment_state = "unavailable";
    const readable = member("readable");
    readable.content!.representative_comment_state = "readable";
    readable.content!.representative_comment = {
      id: "comment",
      root_content_id: "root",
      parent_content_id: "parent",
      parent_relation_status: "observed",
      observation: {
        ...readable.content!.observation,
        content_version: {
          ...readable.content!.observation.content_version!,
          body: "真实评论正文",
        },
        canonical_url: "javascript:unsafe",
        final_url: "https://source.example/comment",
      },
    };
    expect(
      memberComments([
        none,
        unavailable,
        readable,
        { ...readable, id: "other" },
      ]),
    ).toEqual([
      expect.objectContaining({ id: "none", state: "none", body: null }),
      expect.objectContaining({
        id: "unavailable",
        state: "unavailable",
        body: null,
      }),
      expect.objectContaining({
        id: "comment",
        state: "readable",
        body: "真实评论正文",
        originalUrl: "https://source.example/comment",
      }),
    ]);
  });
});

it("orders actual heat hours, preserves known zero, and leaves unknown source heat as a gap", () => {
  const history = [
    heat("2026-10-02T03:00:00Z", 8),
    { ...heat("2026-10-02T02:00:00Z", 0), participant_count: 0 },
    heat("2026-10-02T01:00:00Z", 0),
    heat("invalid", 90),
    heat("2026-10-02T03:00:00Z", 10),
  ];
  expect(heatHistoryPoints(history)).toEqual([
    { time: Date.parse("2026-10-02T01:00:00Z"), heat: 0 },
    { time: Date.parse("2026-10-02T02:00:00Z"), heat: null },
    { time: Date.parse("2026-10-02T03:00:00Z"), heat: 10 },
  ]);
});
