// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import LeaderboardPage, { generateMetadata } from "@/app/leaderboard/page";
import CategoryPage from "@/app/leaderboard/category/[board]/page";
import ModelPage from "@/app/leaderboard/models/[slug]/page";
import SourcePage from "@/app/leaderboard/sources/[sourceKey]/page";
import SourcesPage from "@/app/leaderboard/sources/page";
import RulesPage from "@/app/leaderboard/rules/page";
import LeaderboardLayout from "@/app/leaderboard/layout";
import { ApiRequestError } from "@/request";
import { board } from "../../components/leaderboard/fixtures";

const api = vi.hoisted(() => ({
  getLeaderboardBoard: vi.fn(),
  getLeaderboardModel: vi.fn(),
  getLeaderboardSource: vi.fn(),
  listLeaderboardSources: vi.fn(),
  getLeaderboardRules: vi.fn(),
}));
vi.mock("@/api/moxingbang", () => api);
vi.mock("next/server", () => ({ connection: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

function expectPageTitle(title: string) {
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(screen.getByRole("heading", { level: 1, name: title }).tagName).toBe(
    "H1",
  );
}

function expectBoardStateOrder(stateTitle: string) {
  expectPageTitle("模型榜");
  const title = screen.getByRole("heading", { level: 1, name: "模型榜" });
  const dimension = screen.getByRole("radiogroup", { name: "榜单维度" });
  const filters = screen.getByRole("form", { name: "模型筛选" });
  const state = screen.getByRole("heading", { level: 2, name: stateTitle });
  expect(
    title.compareDocumentPosition(dimension) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(
    dimension.compareDocumentPosition(filters) &
      Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(
    filters.compareDocumentPosition(state) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
}

it("reads the public board using only the existing generated function and applied flags", async () => {
  api.getLeaderboardBoard.mockResolvedValue(board);
  render(
    await LeaderboardPage({
      searchParams: Promise.resolve({ domestic: "true", open_weights: "true" }),
    }),
  );
  expect(api.getLeaderboardBoard).toHaveBeenCalledWith({
    board: "overall",
    domestic: true,
    open_weights: true,
  });
  expectPageTitle("模型榜");
  expect(screen.getByText(/发布轮次：/)).toBeTruthy();
  expect(screen.getByRole("table")).toBeTruthy();
  expect(screen.getByText("7")).toBeTruthy();
});

it("keeps the header and filters before failed requests with usable sidebar routes", async () => {
  api.getLeaderboardBoard.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status: 503,
      code: "database_unavailable",
      requestId: "00000000-0000-4000-8000-000000000003",
      message: "failure",
    }),
  );
  render(
    <LeaderboardLayout>
      {await LeaderboardPage({
        searchParams: Promise.resolve({
          domestic: "true",
          open_weights: "true",
        }),
      })}
    </LeaderboardLayout>,
  );
  expectBoardStateOrder("暂时无法读取模型榜");
  expect(screen.queryByText(/发布轮次：/)).toBeNull();
  expect(screen.getByRole("alert")).toBeTruthy();
  expect(screen.getByText("database_unavailable · 503")).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "重新加载" }).getAttribute("href"),
  ).toBe("/leaderboard?domestic=true&open_weights=true");
  expect(
    screen.getByRole("link", { name: /计算规则/ }).getAttribute("href"),
  ).toBe("/leaderboard/rules");
  expect(screen.getByRole("radio", { name: "编程" })).toBeTruthy();
  expect(
    (await generateMetadata({ searchParams: Promise.resolve({}) })).robots,
  ).toEqual({ index: false, follow: false });
});

it.each(["coding", "reasoning", "knowledge", "professional"])(
  "preserves %s category and filter parameters on failure",
  async (category) => {
    api.getLeaderboardBoard.mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        status: 503,
        code: "database_unavailable",
        message: "failure",
      }),
    );
    render(
      await CategoryPage({
        params: Promise.resolve({ board: category }),
        searchParams: Promise.resolve({
          domestic: "true",
          open_weights: "true",
        }),
      }),
    );
    expectBoardStateOrder("暂时无法读取模型榜");
    expect(api.getLeaderboardBoard).toHaveBeenCalledWith({
      board: category,
      domestic: true,
      open_weights: true,
    });
    expect(
      screen.getByRole("link", { name: "重新加载" }).getAttribute("href"),
    ).toBe(`/leaderboard/category/${category}?domestic=true&open_weights=true`);
  },
);

it("rejects unknown dimensions without requesting an invented board", async () => {
  await expect(
    CategoryPage({
      params: Promise.resolve({ board: "long-context" }),
      searchParams: Promise.resolve({}),
    }),
  ).rejects.toThrow("NEXT_NOT_FOUND");
  expect(api.getLeaderboardBoard).not.toHaveBeenCalled();
});

it("handles missing models and sources through the public-record empty state", async () => {
  const missing = new ApiRequestError({
    kind: "http",
    status: 404,
    code: "not_found",
    message: "absent",
  });
  api.getLeaderboardModel.mockRejectedValue(missing);
  api.getLeaderboardSource.mockRejectedValue(missing);
  const { rerender } = render(
    await ModelPage({ params: Promise.resolve({ slug: "missing-model" }) }),
  );
  expectPageTitle("模型证据");
  expect(
    screen.getByRole("heading", { level: 2, name: "没有这条公开记录" }),
  ).toBeTruthy();
  expect(api.getLeaderboardModel).toHaveBeenCalledWith({
    slug: "missing-model",
  });
  expect(screen.getByRole("status", { name: "没有这条公开记录" })).toBeTruthy();
  rerender(
    await SourcePage({
      params: Promise.resolve({ sourceKey: "missing-source" }),
    }),
  );
  expectPageTitle("评测来源明细");
  expect(
    screen.getByRole("heading", { level: 2, name: "没有这条公开记录" }),
  ).toBeTruthy();
  expect(api.getLeaderboardSource).toHaveBeenCalledWith({
    source_key: "missing-source",
  });
  expect(screen.getByRole("status", { name: "没有这条公开记录" })).toBeTruthy();
});

it("handles source-directory and rules failures independently", async () => {
  const unavailable = new ApiRequestError({
    kind: "network",
    message: "offline",
  });
  api.listLeaderboardSources.mockRejectedValue(unavailable);
  api.getLeaderboardRules.mockRejectedValue(unavailable);
  const { rerender } = render(await SourcesPage());
  expectPageTitle("评测来源与覆盖");
  expect(
    screen.getByRole("heading", { level: 2, name: "暂时无法读取模型榜" }),
  ).toBeTruthy();
  expect(api.listLeaderboardSources).toHaveBeenCalledOnce();
  expect(
    screen.getByRole("link", { name: "重新加载" }).getAttribute("href"),
  ).toBe("/leaderboard/sources");
  rerender(await RulesPage());
  expectPageTitle("计算规则与证据边界");
  expect(
    screen.getByRole("heading", { level: 2, name: "暂时无法读取模型榜" }),
  ).toBeTruthy();
  expect(api.getLeaderboardRules).toHaveBeenCalledOnce();
  expect(
    screen.getByRole("link", { name: "重新加载" }).getAttribute("href"),
  ).toBe("/leaderboard/rules");
});

it.each(["coding", "reasoning", "knowledge", "professional"] as const)(
  "keeps a single fixed page title for normal and empty %s boards",
  async (category) => {
    const data = { ...board, board: { ...board.board, key: category } };
    api.getLeaderboardBoard.mockResolvedValue(data);
    const props = {
      params: Promise.resolve({ board: category }),
      searchParams: Promise.resolve({}),
    };
    const { rerender } = render(await CategoryPage(props));
    expectPageTitle("模型榜");
    expect(screen.getByRole("table")).toBeTruthy();
    api.getLeaderboardBoard.mockResolvedValue({ ...data, entries: [] });
    rerender(await CategoryPage(props));
    expectBoardStateOrder("暂无可展示的已发布模型");
  },
);

it("keeps a single page title above an empty overall board", async () => {
  api.getLeaderboardBoard.mockResolvedValue({ ...board, entries: [] });
  render(await LeaderboardPage({ searchParams: Promise.resolve({}) }));
  expectBoardStateOrder("暂无可展示的已发布模型");
});

it.each([
  {
    title: "模型证据",
    renderPage: () =>
      ModelPage({ params: Promise.resolve({ slug: "test-model" }) }),
  },
  { title: "评测来源与覆盖", renderPage: () => SourcesPage() },
  {
    title: "评测来源明细",
    renderPage: () =>
      SourcePage({ params: Promise.resolve({ sourceKey: "test-source" }) }),
  },
  { title: "计算规则与证据边界", renderPage: () => RulesPage() },
])(
  "renders exactly one h1 and a level-two 503 state for $title",
  async ({ title, renderPage }) => {
    const error = new ApiRequestError({
      kind: "http",
      status: 503,
      code: "database_unavailable",
      message: "failure",
    });
    for (const method of Object.values(api)) method.mockRejectedValue(error);
    render(await renderPage());
    expectPageTitle(title);
    expect(
      screen.getByRole("heading", { level: 2, name: "暂时无法读取模型榜" }),
    ).toBeTruthy();
    expect(screen.getByText("database_unavailable · 503")).toBeTruthy();
  },
);
