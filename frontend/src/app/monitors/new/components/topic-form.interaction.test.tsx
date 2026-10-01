// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({
  sources: vi.fn(),
  create: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/api/jiankongzhuti", () => ({ createMonitorTopic: api.create }));
vi.mock("@/api/laiyuannengli", () => ({ listSourceCapabilities: api.sources }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: api.replace, refresh: api.refresh }),
}));
vi.mock("@/components/monitors/topic-rule-preview", () => ({
  TopicRulePreview: () => null,
}));
import { ApiRequestError } from "@/request";
import { TopicForm } from "./topic-form";
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

describe("core topic creation", () => {
  it("keeps the draft editable when sources fail and retries without erasing inputs", async () => {
    api.sources
      .mockRejectedValueOnce(
        new ApiRequestError({
          kind: "http",
          status: 503,
          code: "service_unavailable",
          message: "来源暂不可用",
          requestId: "source-error",
        }),
      )
      .mockResolvedValueOnce({ items: [], next_cursor: null });
    render(<TopicForm />);
    fireEvent.change(screen.getByLabelText("主题名称"), {
      target: { value: "AI 工具" },
    });
    fireEvent.change(screen.getByLabelText("想关注的关键词"), {
      target: { value: "AI" },
    });
    await screen.findByText("请求编号：source-error");
    expect((screen.getByLabelText("主题名称") as HTMLInputElement).value).toBe(
      "AI 工具",
    );
    fireEvent.click(screen.getByRole("button", { name: "重新读取来源" }));
    await screen.findByText(
      "还没有可选来源。先到来源设置应用搜索预设，或保存后再设置。",
    );
    expect(
      (screen.getByLabelText("想关注的关键词") as HTMLTextAreaElement).value,
    ).toBe("AI");
  });

  it("saves without a source through Swagger defaults and blocks duplicate requests", async () => {
    let resolve!: (value: { id: string }) => void;
    api.sources.mockResolvedValueOnce({ items: [], next_cursor: null });
    api.create.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    render(<TopicForm />);
    fireEvent.change(screen.getByLabelText("主题名称"), {
      target: { value: "AI 工具" },
    });
    fireEvent.change(screen.getByLabelText("想关注的关键词"), {
      target: { value: "AI\nAgent" },
    });
    const save = screen.getByRole("button", { name: "保存关注" });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(api.create).toHaveBeenCalledTimes(1);
    expect(api.create.mock.calls[0][0]).toEqual({
      name: "AI 工具",
      match_any: ["AI", "Agent"],
      match_all: [],
      exclude: [],
      source_keys: [],
      collection_interval_seconds: 1800,
    });
    expect(screen.queryByLabelText("每日报告时间")).toBeNull();
    resolve({ id: "persisted-topic" });
    await waitFor(() =>
      expect(api.replace).toHaveBeenCalledWith("/monitors/persisted-topic"),
    );
  });
});
