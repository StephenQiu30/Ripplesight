import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { createManualRunController, TopicRunResult } from "./topic-run-actions";

const accepted: HotKeyAPI.MonitorTopicRunView = {
  operation_id: "operation-1",
  topic_id: "topic-1",
  topic_version: 2,
  sources: [
    { source_key: "hackernews", job_ids: ["job-1"], skip_reason: null },
    { source_key: "google_news", job_ids: [], skip_reason: "budget" },
  ],
};

describe("manual topic run", () => {
  it("keeps one operation and HTTP request during repeated clicks, then starts a new round explicitly", async () => {
    let resolve!: (value: HotKeyAPI.MonitorTopicRunView) => void;
    const send = vi.fn(
      (topicId: string, _input: HotKeyAPI.MonitorTopicRunInput) =>
        new Promise<HotKeyAPI.MonitorTopicRunView>((done) => {
          expect(topicId).toBe("topic-1");
          expect(_input.source_keys).toEqual(["hackernews"]);
          resolve = done;
        }),
    );
    const controller = createManualRunController(send);
    const first = controller.run("topic-1", ["hackernews"]);
    const repeated = controller.run("topic-1", ["hackernews"]);
    expect(send).toHaveBeenCalledTimes(1);
    expect(repeated).toBe(first);
    resolve(accepted);
    expect(await first).toEqual(accepted);
    expect(await controller.run("topic-1", ["hackernews"])).toEqual(accepted);
    expect(send).toHaveBeenCalledTimes(1);
    controller.reset();
    const next = controller.run("topic-1", ["hackernews"]);
    expect(send).toHaveBeenCalledTimes(2);
    expect(send.mock.calls[0][1].operation_id).not.toBe(
      send.mock.calls[1][1].operation_id,
    );
    resolve(accepted);
    await next;
  });

  it("keeps the same operation ID when a network failure is retried", async () => {
    const send = vi
      .fn()
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce(accepted);
    const controller = createManualRunController(send);
    await expect(controller.run("topic-1", ["hackernews"])).rejects.toThrow(
      "network",
    );
    await expect(controller.run("topic-1", ["hackernews"])).resolves.toEqual(
      accepted,
    );
    expect(send.mock.calls[0][1].operation_id).toBe(
      send.mock.calls[1][1].operation_id,
    );
  });

  it("shows accepted jobs and each skipped source reason", () => {
    const html = renderToStaticMarkup(
      createElement(TopicRunResult, {
        result: accepted,
        sourceNames: { hackernews: "Hacker News", google_news: "Google 新闻" },
      }),
    );
    expect(html).toContain("已受理 1 个任务");
    expect(html).toContain('href="/jobs/job-1"');
    expect(html).toContain("Google 新闻");
    expect(html).toContain("预算不足");
  });
});
