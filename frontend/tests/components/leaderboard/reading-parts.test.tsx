// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import LeaderboardLayout from "@/app/leaderboard/layout";
import LeaderboardLoading from "@/app/leaderboard/loading";
import LeaderboardError from "@/app/leaderboard/error";
import LeaderboardNotFound from "@/app/leaderboard/not-found";
import {
  evidenceDate,
  LeaderboardFailure,
  OfficialPrice,
  RunStamp,
  ScoreSupport,
  SourceStatus,
} from "@/components/leaderboard/reading-parts";
import { ApiRequestError } from "@/request";
import { BoardPageFrame } from "@/components/leaderboard/page-header";

const route = vi.hoisted(() => ({
  pathname: "/leaderboard",
  search: "",
  push: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => route.pathname,
  useSearchParams: () => new URLSearchParams(route.search),
  useRouter: () => ({ push: route.push }),
}));
beforeEach(() => {
  route.pathname = "/leaderboard";
  route.search = "";
  route.push.mockReset();
});

const requestId = "00000000-0000-4000-8000-000000000003";
afterEach(cleanup);

it("shows 503 and request ID below the header and filters while the sidebar works", () => {
  const { container } = render(
    <LeaderboardLayout>
      <BoardPageFrame board="overall" domestic openWeights={false}>
        <LeaderboardFailure
          error={
            new ApiRequestError({
              kind: "http",
              status: 503,
              code: "database_unavailable",
              requestId,
              message: "unavailable",
            })
          }
          href="/leaderboard?domestic=true"
        />
      </BoardPageFrame>
    </LeaderboardLayout>,
  );
  const column = container.firstElementChild!.firstElementChild!;
  expect(column.firstElementChild!.querySelector('[role="alert"]')).toBe(
    screen.getByRole("alert"),
  );
  expect(column.className).not.toMatch(/min-h|h-screen|items-center/);
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  const title = screen.getByRole("heading", { level: 1, name: "模型榜" });
  const filters = screen.getByRole("form", { name: "模型筛选" });
  const errorTitle = screen.getByRole("heading", {
    level: 2,
    name: "暂时无法读取模型榜",
  });
  expect(
    title.compareDocumentPosition(filters) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(
    filters.compareDocumentPosition(errorTitle) &
      Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(screen.getByText("database_unavailable · 503")).toBeTruthy();
  expect(screen.getByText(requestId)).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "重新加载" }).getAttribute("href"),
  ).toBe("/leaderboard?domestic=true");
  const sidebar = screen.getByRole("complementary", { name: "模型榜阅读入口" });
  expect(sidebar.querySelector('a[href="/leaderboard/sources"]')).toBeTruthy();
  expect(sidebar.querySelector('a[href="/leaderboard/rules"]')).toBeTruthy();
  expect(screen.queryByText("Codex 公告")).toBeNull();
});

it.each([401, 403])(
  "renders an unexpected %s rejection without making public reading require login",
  (status) => {
    render(
      <LeaderboardFailure
        error={
          new ApiRequestError({
            kind: "http",
            status,
            code: "permission_denied",
            requestId,
            message: "denied",
          })
        }
        href="/leaderboard"
      />,
    );
    expect(
      screen.getByRole("status", { name: "暂时无法访问公开模型榜" }),
    ).toBeTruthy();
    expect(screen.getByText(/通常无需登录/)).toBeTruthy();
    expect(screen.getByText(`permission_denied · ${status}`)).toBeTruthy();
    expect(screen.getByText(requestId)).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "返回首页" }).getAttribute("href"),
    ).toBe("/");
  },
);

it("treats a missing model as empty but a generic 404 read as an error", () => {
  const error = new ApiRequestError({
    kind: "http",
    status: 404,
    code: "not_found",
    message: "absent",
  });
  const { rerender } = render(
    <LeaderboardFailure
      error={error}
      href="/leaderboard/models/missing"
      resource
    />,
  );
  expect(screen.getByRole("status", { name: "没有这条公开记录" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "重新加载" })).toBeNull();
  rerender(<LeaderboardFailure error={error} href="/leaderboard" />);
  expect(screen.getByRole("alert")).toBeTruthy();
});

it.each([
  ["timeout", "本次读取超时"],
  ["network", "暂时无法连接榜单服务"],
  ["protocol", "服务返回的数据不符合约定"],
] as const)("handles %s by the error kind", (kind, message) => {
  render(
    <LeaderboardFailure
      error={new ApiRequestError({ kind, message: "do not branch on this" })}
      href="/leaderboard"
    />,
  );
  expect(screen.getByText(new RegExp(message))).toBeTruthy();
});

it("renders a labelled fixed-scale bar and its numeric value", () => {
  render(<ScoreSupport score={69.4} label="测试模型支持指数" />);
  expect(screen.getByText("69.4")).toBeTruthy();
  const progress = screen.getByRole("progressbar", {
    name: "测试模型支持指数",
  });
  expect(progress.getAttribute("aria-valuenow")).toBe("69.4");
  expect(progress.getAttribute("aria-valuemax")).toBe("100");
  expect(progress.getAttribute("aria-valuetext")).toContain("不是获胜概率");
});

it("shows the unpublished registry and does not fill missing dates", () => {
  render(<RunStamp run={null} />);
  expect(screen.getByText(/尚无已发布轮次/)).toBeTruthy();
  expect(evidenceDate(null)).toBe("未知");
  expect(evidenceDate("not-a-date")).toBe("未知");
  expect(evidenceDate("2026-10-02T01:00:00Z")).toContain("09:00");
});

it("keeps unknown prices distinct from a verified zero and preserves the source", () => {
  const price: HotKeyAPI.PriceView = {
    currency: "USD",
    input_price: 0,
    output_price: null,
    cached_input_price: null,
    cny_input_price: null,
    cny_output_price: null,
    cny_cached_input_price: null,
    source_url: "https://example.com/prices",
    verified_on: "2026-10-02",
  };
  const { rerender } = render(<OfficialPrice price={null} compact />);
  expect(screen.getByText("暂无公开价格")).toBeTruthy();
  rerender(<OfficialPrice price={price} />);
  expect(screen.getByText(/\$0.00 \/ —/)).toBeTruthy();
  expect(
    screen.getByRole("link", { name: /官方价格/ }).getAttribute("href"),
  ).toBe(price.source_url);
});

it.each([
  ["ranked", "参与排名"],
  ["cross_reference", "交叉参考"],
  ["observing", "观察中"],
  ["reference_only", "仅供参考"],
  ["awaiting", "等待成绩"],
  ["unknown", "unknown"],
])("labels source status %s", (status, label) => {
  render(
    <SourceStatus
      source={{
        key: "test",
        name: "测试来源",
        status,
        operator: "测试机构",
        description: "测试说明",
        brand: { src: null, monogram: "T" },
        weight: 0.1,
        family_key: null,
        category_key: null,
        collected: false,
      }}
    />,
  );
  expect(screen.getByText(label)).toBeTruthy();
});

it("provides a loading boundary with accessible busy state", () => {
  render(<LeaderboardLoading />);
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(
    screen.getByRole("heading", { level: 1, name: "模型榜" }),
  ).toBeTruthy();
  expect(screen.queryByText(/发布轮次：/)).toBeNull();
  expect(
    screen
      .getByRole("status", { name: "正在读取模型榜" })
      .getAttribute("aria-busy"),
  ).toBe("true");
});

it("keeps sidebar entries available for the render-error and missing-route boundaries", () => {
  const { rerender } = render(
    <LeaderboardLayout>
      <LeaderboardError error={new Error("render")} reset={() => {}} />
    </LeaderboardLayout>,
  );
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(
    screen.getByRole("heading", { level: 2, name: "模型榜页面未完成加载" }),
  ).toBeTruthy();
  expect(screen.getByRole("link", { name: /计算规则/ })).toBeTruthy();
  rerender(
    <LeaderboardLayout>
      <LeaderboardNotFound />
    </LeaderboardLayout>,
  );
  expect(
    screen.getByRole("status", { name: "没有这项榜单或公开记录" }),
  ).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "返回模型榜" }).getAttribute("href"),
  ).toBe("/leaderboard");
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(
    screen.getByRole("heading", { level: 2, name: "没有这项榜单或公开记录" }),
  ).toBeTruthy();
});

it.each([
  ["/leaderboard", "模型榜"],
  ["/leaderboard/category/coding", "模型榜"],
  ["/leaderboard/category/reasoning", "模型榜"],
  ["/leaderboard/category/knowledge", "模型榜"],
  ["/leaderboard/category/professional", "模型榜"],
  ["/leaderboard/models/test-model", "模型证据"],
  ["/leaderboard/sources", "评测来源与覆盖"],
  ["/leaderboard/sources/test-source", "评测来源明细"],
  ["/leaderboard/rules", "计算规则与证据边界"],
])(
  "keeps one page heading for the loading and error boundaries at %s",
  (pathname, title) => {
    route.pathname = pathname;
    route.search = "domestic=true&open_weights=true";
    const { rerender } = render(<LeaderboardLoading />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeTruthy();
    expect(screen.getByRole("status", { name: "正在读取模型榜" })).toBeTruthy();
    rerender(
      <LeaderboardError error={new Error("render failure")} reset={() => {}} />,
    );
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeTruthy();
    const errorTitle = screen.getByRole("heading", {
      level: 2,
      name: "模型榜页面未完成加载",
    });
    if (pathname === "/leaderboard" || pathname.includes("/category/")) {
      const filters = screen.getByRole("form", { name: "模型筛选" });
      expect(
        filters.compareDocumentPosition(errorTitle) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(
        screen
          .getByRole("checkbox", { name: "国内模型" })
          .getAttribute("aria-checked"),
      ).toBe("true");
      expect(
        screen
          .getByRole("checkbox", { name: "开放权重" })
          .getAttribute("aria-checked"),
      ).toBe("true");
      fireEvent.click(
        screen.getByRole("radio", {
          name: pathname.endsWith("knowledge") ? "编程" : "知识",
        }),
      );
      expect(route.push).toHaveBeenCalledWith(
        `/leaderboard/category/${pathname.endsWith("knowledge") ? "coding" : "knowledge"}?domestic=true&open_weights=true`,
      );
    } else {
      expect(screen.queryByRole("form", { name: "模型筛选" })).toBeNull();
    }
  },
);
