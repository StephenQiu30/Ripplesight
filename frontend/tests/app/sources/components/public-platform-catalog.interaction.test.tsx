// @vitest-environment happy-dom

import { act } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ read: vi.fn() }));
const notifications = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock("@/api/laiyuannengli", () => ({ listPublicPlatformCatalog: api.read }));
vi.mock("sonner", () => ({ toast: notifications }));

import { PublicPlatformCatalog } from "@/app/sources/components/public-platform-catalog";
import { ApiRequestError } from "@/request";

const entry: HotKeyAPI.PublicPlatformEntryView = {
  entry_key: "threads.search",
  display_name: "标签与搜索订阅流",
  status: "candidate",
  query_mode: "tag_feed",
  object_scope: "公开页面标签候选",
  time_range: "有界快照",
  sort_order: "尚未验证",
  pagination: "未验证可信尾段",
  limitations: ["标签结果不冒充公共关键词全站搜索。"],
  admission_requirements: ["允许用途和删除合同待验证。"],
  block_reason: "用途和稳定性待验证。",
  supplier_fee_cap_micros: 0,
  fee_status: "unverified",
  execution_admitted: false,
  trial_verified: false,
  product_available: false,
  last_persisted_success_at: null,
  route_template: "/threads/search/:keyword",
  evidence_urls: ["https://example.com/fixed-source"],
  capabilities: [
    {
      capability: "keyword_search",
      display_name: "关键词检索",
      documented_support: "unknown",
      execution_admitted: false,
      trial_verified: false,
      product_available: false,
    },
  ],
};
const platforms: HotKeyAPI.PublicPlatformCatalogView[] = (
  [
    ["x", "X"],
    ["instagram", "Instagram"],
    ["facebook", "Facebook"],
    ["threads", "Threads"],
    ["douyin", "抖音"],
    ["bilibili", "Bilibili"],
    ["weibo", "微博"],
  ] as const
).map(([key, name]) => ({
  platform_key: key,
  display_name: name,
  scope_description: "免费入口候选，不授予执行权限。",
  inspected_component: "rsshub",
  inspected_revision: "0a3a66a1cb28a645ffe90577a68411886274a2ee",
  inspected_at: "2026-10-04",
  entries: [
    {
      ...entry,
      entry_key: `${key}.candidate`,
      status:
        key === "facebook" ? "missing" : key === "x" ? "blocked" : "candidate",
      route_template: key === "threads" ? entry.route_template : null,
      fee_status: key === "x" ? "disallowed" : "unverified",
    },
  ],
}));

beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  api.read.mockResolvedValue({ items: platforms, next_cursor: null });
});
afterEach(cleanup);

describe("public platform research directory", () => {
  it("shows all seven with honest candidate states and cannot configure or execute them", async () => {
    render(<PublicPlatformCatalog />);
    await screen.findByRole("heading", { name: "Threads" });
    for (const platform of platforms) {
      expect(
        screen.getByRole("heading", { name: platform.display_name }),
      ).toBeTruthy();
    }
    expect(screen.getByText("入口待确认")).toBeTruthy();
    expect(screen.getByText("暂不可执行")).toBeTruthy();
    expect(screen.getAllByText("尚无记录")).toHaveLength(7);
    expect(screen.getAllByText("（入口零费用待核实）")).toHaveLength(6);
    expect(
      screen.queryByRole("button", { name: /启用|连接|立即运行|采集/ }),
    ).toBeNull();
    expect(screen.queryByText("/threads/search/:keyword")).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "查看Threads入口详情" }),
    );
    expect(await screen.findByText("/threads/search/:keyword")).toBeTruthy();
    expect(screen.getByText("标签结果不冒充公共关键词全站搜索。")).toBeTruthy();
    expect(screen.getByText("未通过")).toBeTruthy();
    expect(screen.getByText("尚未上线")).toBeTruthy();
    expect(screen.queryByText("已可用")).toBeNull();
    expect(api.read).toHaveBeenCalledTimes(1);
  });

  it("preserves the last catalog on read failure and retries only the directory GET", async () => {
    render(<PublicPlatformCatalog />);
    await screen.findByRole("heading", { name: "Threads" });
    api.read.mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 503,
        message: "目录暂不可用",
        requestId: "catalog-request-1",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "刷新平台目录" }));
    await waitFor(() =>
      expect(notifications.error).toHaveBeenCalledWith(
        "目录暂不可用 请求编号：catalog-request-1",
      ),
    );
    expect(screen.getByRole("heading", { name: "Threads" })).toBeTruthy();
    expect(
      screen.getByText("当前为上次读取的资料，请刷新后再核对。"),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重新加载平台目录" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(api.read).toHaveBeenCalledTimes(3);
  });

  it("aborts on unmount and discards a late catalog result", async () => {
    let finish!: (page: {
      items: HotKeyAPI.PublicPlatformCatalogView[];
      next_cursor: null;
    }) => void;
    api.read.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const view = render(<PublicPlatformCatalog />);
    const signal = api.read.mock.calls[0][0].signal as AbortSignal;
    view.unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => finish({ items: platforms, next_cursor: null }));
    expect(screen.queryByText("Threads")).toBeNull();
    expect(notifications.error).not.toHaveBeenCalled();
  });

  it("shows an honest empty directory instead of reporting a platform has no updates", async () => {
    api.read.mockResolvedValue({ items: [], next_cursor: null });
    render(<PublicPlatformCatalog />);
    expect(await screen.findByText("平台目录暂为空")).toBeTruthy();
    expect(screen.queryByText("没有新内容")).toBeNull();
  });
});
