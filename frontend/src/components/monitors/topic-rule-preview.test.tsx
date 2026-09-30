// @vitest-environment happy-dom

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  samples: vi.fn(),
  title: vi.fn(),
}));
vi.mock("@/api/jiankongzhuti", () => ({
  previewMonitorTopicSamples: api.samples,
  previewMonitorTopic: api.title,
}));

import { ApiRequestError } from "@/request";
import { TopicRulePreview } from "./topic-rule-preview";

const preview: HotKeyAPI.ContentSamplePreviewView = {
  rules: { match_any: ["AI"], match_all: [], exclude: ["招聘"] },
  rule_basis: "draft",
  source_keys: ["hackernews"],
  starts_at: "2026-09-23T00:00:00Z",
  ends_at: "2026-09-30T00:00:00Z",
  sample_limit: 20,
  sample_status: "available",
  truncated: false,
  external_requests: 0,
  model_requests: 0,
  samples: [
    {
      content_id: "content-1",
      observation_id: "observation-1",
      content_version_id: "version-1",
      source_key: "hackernews",
      title: "AI 招聘",
      body_excerpt: "已有正文摘录",
      excerpt_truncated: true,
      published_at: null,
      observed_at: "2026-09-29T00:00:00Z",
      matched: false,
      matched_any: ["AI"],
      matched_all: [],
      excluded_by: ["招聘"],
    },
  ],
};
const props = {
  matchAny: "AI",
  matchAll: "",
  exclude: "招聘",
  sourceKeys: ["hackernews"],
};
function openPreview() {
  fireEvent.click(screen.getByRole("button", { name: "预览规则" }));
}
function readSamples() {
  fireEvent.click(screen.getByRole("button", { name: "预览已采集内容" }));
}
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("persisted rule samples", () => {
  it("sends the draft and sources, explains exclusions and links the saved content without submitting the title checker", async () => {
    api.samples.mockResolvedValue(preview);
    render(<TopicRulePreview {...props} />);
    openPreview();
    readSamples();
    await waitFor(() => expect(screen.getByText("已排除")).toBeTruthy());
    expect(api.samples).toHaveBeenCalledWith({
      match_any: ["AI"],
      match_all: [],
      exclude: ["招聘"],
      source_keys: ["hackernews"],
    });
    expect(
      screen.getByRole("link", { name: "AI 招聘" }).getAttribute("href"),
    ).toBe("/content/content-1");
    expect(screen.getByText(/匹配依据为完整已保存文字/)).toBeTruthy();
    expect(screen.getByText(/未保存的草稿规则/)).toBeTruthy();
    expect(api.title).not.toHaveBeenCalled();
  });

  it("labels an empty local window as insufficient evidence", async () => {
    api.samples.mockResolvedValue({
      ...preview,
      samples: [],
      sample_status: "insufficient_samples",
    });
    render(<TopicRulePreview {...props} />);
    openPreview();
    readSamples();
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toContain(
        "不能据此判断源站无结果",
      ),
    );
  });

  it("prevents duplicate requests and discards an old response after draft or source changes", async () => {
    let resolve!: (value: HotKeyAPI.ContentSamplePreviewView) => void;
    api.samples.mockReturnValueOnce(
      new Promise<HotKeyAPI.ContentSamplePreviewView>((done) => {
        resolve = done;
      }),
    );
    const view = render(<TopicRulePreview {...props} />);
    openPreview();
    readSamples();
    fireEvent.click(screen.getByRole("button", { name: "正在读取样本" }));
    expect(api.samples).toHaveBeenCalledOnce();
    view.rerender(
      <TopicRulePreview
        {...props}
        matchAny="Agent"
        sourceKeys={["bilibili"]}
      />,
    );
    await act(async () => resolve(preview));
    openPreview();
    expect(screen.queryByText("AI 招聘")).toBeNull();
    api.samples.mockResolvedValue({
      ...preview,
      samples: [],
      sample_status: "insufficient_samples",
    });
    readSamples();
    await waitFor(() => expect(api.samples).toHaveBeenCalledTimes(2));
    expect(api.samples.mock.calls[1][0]).toEqual({
      match_any: ["Agent"],
      match_all: [],
      exclude: ["招聘"],
      source_keys: ["bilibili"],
    });
  });

  it("preserves business error messages and request IDs through a retry", async () => {
    api.samples.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 500,
        code: "internal_error",
        message: "暂时无法读取样本",
        requestId: "request-059",
      }),
    );
    render(<TopicRulePreview {...props} />);
    openPreview();
    readSamples();
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("request-059"),
    );
    api.samples.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 503,
        code: "demo_scope_conflict",
        message: "存在多个历史数据分区，无法读取样本",
        requestId: "request-demo-scope",
      }),
    );
    readSamples();
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain(
        "存在多个历史数据分区，无法读取样本",
      );
      expect(screen.getByRole("alert").textContent).toContain(
        "request-demo-scope",
      );
    });
    api.samples.mockResolvedValueOnce(preview);
    readSamples();
    expect(await screen.findByText("AI 招聘")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
