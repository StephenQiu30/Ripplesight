// @vitest-environment happy-dom
import { expectOnePageHeading } from "../../../../page-heading";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));
afterEach(() => vi.clearAllMocks());

const api = vi.hoisted(() => ({
  sources: vi.fn(),
  create: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("@/api/jiankongzhuti", () => ({
  createMonitorTopic: api.create,
  listMonitorEditorialSources: () => Promise.resolve([]),
}));
vi.mock("@/api/laiyuannengli", () => ({ listSourceCapabilities: api.sources }));
vi.mock("next/server", () => ({ connection: () => Promise.resolve() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: api.replace, refresh: api.refresh }),
}));
vi.mock("@/components/monitors/topic-rule-preview", () => ({
  TopicRulePreview: () => null,
}));
import { ApiRequestError } from "@/request";
import { TopicForm } from "@/app/monitors/new/components/topic-form";
import { searchPlatform } from "../../../../components/monitors/search-contract-fixture";
beforeEach(() => vi.resetAllMocks());
afterEach(() => {
  if (document.body.textContent) expectOnePageHeading();
  cleanup();
});

describe("core topic creation", () => {
  it("explains current source filters without saving or collecting", async () => {
    api.sources.mockResolvedValue({
      items: [searchPlatform],
      next_cursor: null,
    });
    render(<TopicForm />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Hacker News查询范围与筛选" }),
    );
    expect(screen.getByText("当前连接 v7")).toBeTruthy();
    expect(screen.getByText("全部包含 · 仅本地精筛")).toBeTruthy();
    expect(
      screen
        .getByRole("switch", { name: "Hacker News" })
        .getAttribute("aria-checked"),
    ).toBe("false");
    expect(api.create).not.toHaveBeenCalled();
  });
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
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith("来源暂不可用", {
        description: "请求编号：source-error",
      }),
    );
    expect(screen.queryByText("来源暂不可用")).toBeNull();
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
    expect(
      screen.getByLabelText("每日报告时间").closest("fieldset")?.disabled,
    ).toBe(true);
    fireEvent.click(save);
    fireEvent.click(save);
    expect(api.create).toHaveBeenCalledTimes(1);
    expect(api.create.mock.calls[0][0]).toEqual({
      search_language: "any",
      search_window_seconds: 86400,
      max_queries: 50,
      max_items_per_query: 100,
      max_requests_per_query: 100,
      name: "AI 工具",
      match_any: ["AI", "Agent"],
      match_all: [],
      exclude: [],
      source_keys: [],
      editorial_profile_ids: [],
      collection_interval_seconds: 3600,
      report_time: "08:00:00",
      weekly_report_enabled: true,
      notification_target_names: [],
    });
    resolve({ id: "persisted-topic" });
    await waitFor(() =>
      expect(api.replace).toHaveBeenCalledWith("/monitors/persisted-topic"),
    );
  });
});

it.each([
  { q: "  芯片 & C++  ", expected: "芯片 & C++" },
  { q: ["芯片", "模型"], expected: "" },
  { q: "x".repeat(201), expected: "" },
])(
  "seeds only a bounded single search phrase without creating a topic",
  async ({ q, expected }) => {
    api.sources.mockResolvedValue({ items: [], next_cursor: null });
    const { default: NewMonitorTopicPage } =
      await import("@/app/monitors/new/page");
    render(await NewMonitorTopicPage({ searchParams: Promise.resolve({ q }) }));
    expect(
      (screen.getByLabelText("想关注的关键词") as HTMLTextAreaElement).value,
    ).toBe(expected);
    await waitFor(() => expect(api.sources).toHaveBeenCalled());
    expect(api.create).not.toHaveBeenCalled();
  },
);

it("refreshes platform choices after connection without losing the keyword draft", async () => {
  api.sources.mockResolvedValueOnce({ items: [], next_cursor: null });
  render(<TopicForm />);
  fireEvent.change(screen.getByLabelText("想关注的关键词"), {
    target: { value: "我自己的关键词" },
  });
  await screen.findByRole("button", { name: "刷新平台状态" });
  api.sources.mockResolvedValueOnce({
    items: [
      {
        source_key: "bilibili",
        display_name: "B站",
        connection_status: "active",
        has_credentials: false,
        capabilities: [
          {
            capability: "search",
            display_name: "关键词搜索",
            scheduled: {
              status: "pending_verification",
              next_action: "待验证",
            },
          },
        ],
      },
    ],
    next_cursor: null,
  });
  fireEvent.click(screen.getByRole("button", { name: "刷新平台状态" }));
  const platform = await screen.findByRole("switch", { name: "B站" });
  expect(platform.hasAttribute("disabled")).toBe(false);
  expect(
    (screen.getByLabelText("想关注的关键词") as HTMLTextAreaElement).value,
  ).toBe("我自己的关键词");
  expect(api.create).not.toHaveBeenCalled();
});

it("saves custom collection bounds and rejects invalid drafts without requests", async () => {
  api.sources.mockResolvedValue({ items: [], next_cursor: null });
  api.create.mockResolvedValue({ id: "custom-topic" });
  render(<TopicForm />);
  fireEvent.change(screen.getByLabelText("主题名称"), {
    target: { value: "限制测试" },
  });
  fireEvent.change(screen.getByLabelText("想关注的关键词"), {
    target: { value: "AI" },
  });
  fireEvent.change(screen.getByLabelText("搜索窗口（秒）"), {
    target: { value: "599" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存关注" }));
  expect(api.create).not.toHaveBeenCalled();
  expect(
    screen.getByLabelText("搜索窗口（秒）").getAttribute("aria-invalid"),
  ).toBe("true");
  fireEvent.change(screen.getByLabelText("搜索窗口（秒）"), {
    target: { value: "1800" },
  });
  fireEvent.change(screen.getByLabelText("每来源每轮查询上限"), {
    target: { value: "2" },
  });
  fireEvent.change(screen.getByLabelText("每查询候选处理上限"), {
    target: { value: "8" },
  });
  fireEvent.change(screen.getByLabelText("每查询每轮平台请求上限"), {
    target: { value: "1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存关注" }));
  await waitFor(() =>
    expect(api.create).toHaveBeenCalledWith(
      expect.objectContaining({
        search_language: "any",
        search_window_seconds: 1800,
        max_queries: 2,
        max_items_per_query: 8,
        max_requests_per_query: 1,
      }),
    ),
  );
});
