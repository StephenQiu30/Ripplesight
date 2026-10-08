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
  expect(screen.getByText("暂无历史曲线")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "X 今日趋势" })).toBeTruthy();
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
  expect(screen.getByRole("status", { name: "暂无公开事件" })).toBeTruthy();
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
  fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
  expect(navigation.refresh).toHaveBeenCalledOnce();
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
    screen.getByRole("link", { name: "订阅日报" }).getAttribute("href"),
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
