// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { expectOnePageHeading } from "../../page-heading";
const navigation = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
  usePathname: () => "/",
}));
import { HomeContent } from "@/app/components/home-content";
import { publicItem, publicStory } from "./home-fixtures";
afterEach(() => {
  expectOnePageHeading();
  cleanup();
  vi.clearAllMocks();
});
const reading = {
  items: [publicItem],
  stories: [publicStory],
  topics: [],
  editions: [],
  unavailable: [],
  observedAt: "2026-10-08T08:00:00Z",
};
it("renders the Figma event page and reserves missing analytics without inventing totals", () => {
  render(<HomeContent reading={reading} />);
  expect(
    screen.getByRole("heading", { level: 1, name: "今日 AI 热点" }),
  ).toBeTruthy();
  expect(screen.getByRole("region", { name: "热点事件" })).toBeTruthy();
  expect(screen.queryByText("最新资讯")).toBeNull();
  expect(screen.queryByText("让信息围绕你")).toBeNull();
  expect(screen.queryByText("探索专题")).toBeNull();
  expect(screen.getAllByTitle("暂无全站统计")).toHaveLength(4);
  expect(screen.getByText("历史依据未返回")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "事件热度趋势" })).toBeTruthy();
});

it("keeps backend full-site counts independent of category and clears stale counts on failure", () => {
  const overview = {
    total_events: 123,
    new_events_24h: 17,
    updated_events_24h: 9,
    covered_sources: 12,
    time_unknown_events: 2,
    platform_count: null,
    negative_surge_count: null,
  };
  const { rerender } = render(
    <HomeContent
      category="policy"
      reading={{ ...reading, overview, windowStart: "2026-10-07T08:00:00Z" }}
    />,
  );
  const metrics = screen.getByLabelText("今日概览");
  expect(metrics.textContent).toContain("公开事件123");
  expect(metrics.textContent).toContain("24小时新识别17");
  expect(metrics.textContent).toContain("旧事件进展归入9");
  expect(metrics.textContent).toContain("覆盖来源12");
  expect(screen.getByText(/2 个事件时间待核对/)).toBeTruthy();
  expect(screen.getByRole("status", { name: "当前分类暂无事件" })).toBeTruthy();
  rerender(
    <HomeContent
      reading={{
        ...reading,
        overview,
        failures: { stories: { status: 503, code: "database_unavailable" } },
      }}
    />,
  );
  expect(screen.getAllByTitle("暂无全站统计")).toHaveLength(4);
  expect(screen.queryByText(/2 个事件时间待核对/)).toBeNull();
});

it("renders server activity and its basis without deriving it from source publication", () => {
  render(
    <HomeContent
      reading={{
        ...reading,
        stories: [
          {
            ...publicStory,
            reports: [
              ...publicStory.reports,
              {
                ...publicStory.reports[0],
                id: "future-material",
                discovered_at: "2027-01-01T00:00:00Z",
              },
            ],
            timing: {
              snapshot_at: reading.observedAt,
              reference_at: "2026-01-01T00:00:00Z",
              reference_basis: "published",
              identified_at: "2026-10-01T00:00:00Z",
              latest_development_at: "2026-10-08T07:00:00Z",
              development_fact_ids: ["fact-1"],
              activity: "existing_updated",
              occurred_at: null,
            },
          },
        ],
      }}
    />,
  );
  expect(screen.getByText(/旧事件进展归入 · 系统识别/)).toBeTruthy();
  expect(screen.getByText(/来源发布时间.*发生时间未记录/)).toBeTruthy();
  expect(screen.getByText(/进展可能重新归入/)).toBeTruthy();
  expect(screen.getByText(/另有材料发现时间待核对/)).toBeTruthy();
});
it("keeps the category selection in the URL and drops retired pagination state", () => {
  render(<HomeContent category="paper" />);
  fireEvent.click(screen.getByRole("radio", { name: "模型发布" }));
  expect(navigation.push).toHaveBeenCalledWith("/?category=ai-models");
  expect(
    screen.getByRole("radiogroup", { name: "事件分类" }).parentElement
      ?.className,
  ).toContain("overflow-x-auto");
});
it("keeps an empty category honest even when other published events exist", () => {
  render(<HomeContent category="policy" reading={reading} />);
  expect(screen.getByRole("status", { name: "当前分类暂无事件" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "查看全部事件" }));
  expect(navigation.push).toHaveBeenCalledWith("/");
  expect(
    within(screen.getByRole("region", { name: "热点事件" })).queryByRole(
      "link",
      { name: publicStory.title },
    ),
  ).toBeNull();
});
it("does not fall back to the retired article feed when events fail", () => {
  render(
    <HomeContent
      reading={{
        ...reading,
        unavailable: ["stories"],
        failures: { stories: { code: "public_failed", status: 503 } },
      }}
    />,
  );
  expect(screen.getByText("public_failed · 503")).toBeTruthy();
  expect(screen.queryByText(publicItem.title)).toBeNull();
  expect(screen.queryByText("暂无可比较的热度变化。")).toBeNull();
  expect(screen.getByText("事件读取失败，暂时无法比较热度变化。")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
  expect(navigation.refresh).toHaveBeenCalledOnce();
});

it("keeps a failed daily edition recoverable without hiding valid events", () => {
  render(
    <HomeContent
      reading={{
        ...reading,
        unavailable: ["editions"],
        failures: {
          editions: { status: 503, code: "database_unavailable" },
        },
      }}
    />,
  );
  expect(
    within(screen.getByRole("region", { name: "热点事件" })).getByRole("link", {
      name: publicStory.title,
    }),
  ).toBeTruthy();
  expect(screen.getByRole("alert", { name: "日报暂时无法读取" })).toBeTruthy();
  expect(screen.queryByText(/今日日报尚未发布/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重试日报" }));
  expect(navigation.refresh).toHaveBeenCalledOnce();
});

it("keeps unknown negative metrics neutral and offers a useful empty next step", () => {
  render(<HomeContent />);
  expect(screen.getByRole("status", { name: "暂无公开事件" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "探索资讯" })).toBeTruthy();
  screen.getAllByTitle("暂无全站统计").forEach((metric) => {
    expect(metric.className).not.toContain("text-destructive");
  });
});
it("submits search through the real discovery route and keeps the actual RSS subscription", () => {
  render(<HomeContent />);
  const form = screen.getByRole("search") as HTMLFormElement;
  expect(form.getAttribute("action")).toBe("/discover");
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "模型" },
  });
  expect(new FormData(form).get("q")).toBe("模型");
  expect(
    screen.getByRole("link", { name: "订阅 RSS" }).getAttribute("href"),
  ).toBe("/feed/daily.xml");
});
it("reveals additional real events without manufacturing a cursor or global count", () => {
  render(
    <HomeContent
      reading={{
        ...reading,
        stories: Array.from({ length: 8 }, (_, i) => ({
          ...publicStory,
          id: `s${i}`,
          title: `事件${i}`,
        })),
      }}
    />,
  );
  const list = screen.getByRole("list", { name: "热点事件列表" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(6);
  fireEvent.click(screen.getByRole("button", { name: "加载更多事件" }));
  expect(within(list).getAllByRole("listitem")).toHaveLength(8);
  expect(screen.queryByRole("button", { name: "加载更多事件" })).toBeNull();
});

it("distinguishes a denied public response from an empty feed", () => {
  render(
    <HomeContent
      reading={{
        ...reading,
        unavailable: ["stories"],
        failures: { stories: { status: 403, code: "permission_denied" } },
      }}
    />,
  );
  expect(
    screen.getByRole("heading", { name: "无权读取公开事件" }),
  ).toBeTruthy();
  expect(screen.queryByText("暂无公开事件")).toBeNull();
});

it("shows material discovery and sampling limits without calling it a new event or fact", () => {
  render(
    <HomeContent
      reading={{ ...reading, observedAt: "2026-10-06T08:00:00Z" }}
    />,
  );
  const list = screen.getByRole("list", { name: "热点事件列表" });
  expect(within(list).getByText(/24小时内发现材料/)).toBeTruthy();
  expect(within(list).getByText(/含补录材料/)).toBeTruthy();
  expect(within(list).getByText(/事件参考.*最新材料发现/)).toBeTruthy();
  expect(within(list).getByText("个独立来源").textContent).toBe("3 个独立来源");
  expect(within(list).getByText(/1 个来源不可比/)).toBeTruthy();
  expect(within(list).getByText(/部分来源采集不完整/)).toBeTruthy();
  expect(within(list).queryByText(/今日新事件|旧事件更新/)).toBeNull();
  expect(screen.getByText(/最多50条.*分类仅筛选当前集合/)).toBeTruthy();
  const monitor = within(list).getByRole("link", { name: "设置监测" });
  expect(
    new URL(monitor.getAttribute("href")!, "http://localhost").searchParams.get(
      "q",
    ),
  ).toBe(publicStory.title);
  expect(navigation.push).not.toHaveBeenCalled();
  expect(navigation.refresh).not.toHaveBeenCalled();
});

it("offers explicit monitor setup from the empty home", () => {
  render(<HomeContent />);
  expect(
    screen.getByRole("link", { name: "设置关键词监测" }).getAttribute("href"),
  ).toBe("/monitors/new");
});

it("labels the latest edition by its actual period even when an old period was generated recently", () => {
  render(
    <HomeContent
      reading={{
        ...reading,
        editions: [
          {
            kind: "daily",
            key: "2026-10-01",
            title: "十月一日日报",
            revision: 2,
            created_at: "2026-10-08T07:00:00Z",
            reading_url: "/reports/daily/2026-10-01",
          },
        ],
      }}
    />,
  );
  expect(screen.getByRole("heading", { name: "最新日报" })).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "今日日报" })).toBeNull();
  expect(screen.getByText("2026-10-01")).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "十月一日日报" }).getAttribute("href"),
  ).toBe("/reports/daily/2026-10-01");
});

it("does not expose stale event titles, monitors, counts or update times on denial", () => {
  render(
    <HomeContent
      reading={{
        ...reading,
        stories: Array.from({ length: 8 }, (_, i) => ({
          ...publicStory,
          id: `old-${i}`,
        })),
        failures: { stories: { status: 403, code: "permission_denied" } },
      }}
    />,
  );
  expect(screen.queryByText(publicStory.title)).toBeNull();
  expect(screen.queryByRole("link", { name: "设置监测" })).toBeNull();
  expect(screen.queryByRole("button", { name: "加载更多事件" })).toBeNull();
  expect(screen.queryByText(/更新于/)).toBeNull();
  expect(
    screen.getByRole("heading", { name: "无权读取公开事件" }),
  ).toBeTruthy();
});

it("keeps events readable when a denied edition has a newer stale timestamp", () => {
  render(
    <HomeContent
      reading={{
        ...reading,
        editions: [
          {
            kind: "daily",
            key: "2026-10-08",
            title: "不可读的旧日报",
            revision: 1,
            created_at: "2026-10-08T08:00:00Z",
            reading_url: "/reports/daily/2026-10-08",
          },
        ],
        unavailable: ["editions"],
        failures: { editions: { status: 403, code: "permission_denied" } },
      }}
    />,
  );
  expect(screen.queryByText("不可读的旧日报")).toBeNull();
  expect(screen.getByRole("list", { name: "热点事件列表" })).toBeTruthy();
  expect(screen.getByText(/更新于/).textContent).toContain("2026年10月6日");
  expect(
    screen.getByRole("heading", { name: "日报暂时无法读取" }),
  ).toBeTruthy();
});

it.each([
  ["2026-10-09T08:00:00Z", "时间待核对"],
  ["invalid", "时间未知"],
])(
  "does not treat the %s heat window as a valid current observation",
  (end, label) => {
    render(
      <HomeContent
        reading={{
          ...reading,
          stories: [
            {
              ...publicStory,
              attention: { ...publicStory.attention!, window_end: end },
            },
          ],
        }}
      />,
    );
    expect(
      within(screen.getByRole("region", { name: "上升最快" })).getByText(
        "暂无可比较的热度变化。",
      ),
    ).toBeTruthy();
    expect(
      within(screen.getByRole("list", { name: "热点事件列表" })).getByText(
        new RegExp(`48小时窗口截至 ${label}`),
      ),
    ).toBeTruthy();
  },
);
