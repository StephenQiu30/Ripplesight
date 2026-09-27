import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/rebang", () => ({
  getHistoricalHotlistSnapshot: vi.fn(),
  listHotlistSnapshots: vi.fn(),
  listHotlistSources: vi.fn(),
}));

import { getHistoricalHotlistSnapshot } from "@/api/rebang";

import { resolveSnapshotRequest, SnapshotDetail } from "./hotlist-workspace";

const snapshot: HotKeyAPI.HotlistSnapshotView = {
  snapshot_id: "snapshot-2",
  source_key: "hotlist_weibo",
  observed_at: "2026-09-27T11:30:00Z",
  due_at: "2026-09-27T11:30:00Z",
  operation_id: "operation-2",
  entry_count: 2,
  previous_snapshot_id: "snapshot-1",
  gap_count: 1,
  next_cursor: null,
  items: [
    {
      rank: 1,
      title: "AI story",
      url: "https://example.com/ai",
      summary: null,
      heat: null,
      published_at: null,
      content_id: "content-1",
      previous_rank: 3,
      rank_delta: 2,
      rank_change: "up",
      matched: true,
      matched_topic_names: ["AI"],
    },
    {
      rank: 2,
      title: "Unmatched story",
      url: "https://example.com/other",
      summary: null,
      heat: null,
      published_at: null,
      content_id: null,
      previous_rank: null,
      rank_delta: null,
      rank_change: "new",
      matched: false,
      matched_topic_names: [],
    },
  ],
};

describe("hotlist snapshot", () => {
  it("shows the missing due bucket, original ranks, and links only matched content", () => {
    const html = renderToStaticMarkup(
      createElement(SnapshotDetail, { snapshot }),
    );
    expect(html).toContain("此前 1 个采集窗口无快照");
    expect(html).toContain("上升 2");
    expect(html).toContain("新上榜");
    expect(html).toContain("snapshot=snapshot-1");
    expect(html).toContain('href="/content/content-1"');
    expect(html).not.toContain("/content/null");
    expect(html).toContain('href="https://example.com/other"');
  });

  it("distinguishes a successful empty snapshot from no history", () => {
    const html = renderToStaticMarkup(
      createElement(SnapshotDetail, {
        snapshot: { ...snapshot, entry_count: 0, items: [], gap_count: 0 },
      }),
    );
    expect(html).toContain("本次观察到空榜");
    expect(html).toContain("成功的零条目快照");
  });

  it("discards a late response after the user changes the selected snapshot", async () => {
    let finish!: (value: HotKeyAPI.HotlistSnapshotView) => void;
    vi.mocked(getHistoricalHotlistSnapshot).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const controller = new AbortController();
    const result = resolveSnapshotRequest(
      "hotlist_weibo",
      "snapshot-2",
      controller.signal,
    );
    controller.abort();
    finish(snapshot);
    expect(await result).toBeNull();
  });
});
