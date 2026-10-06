// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { BoardFilters } from "@/components/leaderboard/board-filters";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
afterEach(cleanup);
beforeEach(() => push.mockReset());

it("uses the existing dimension URL and preserves both applied filters", () => {
  render(<BoardFilters board="overall" domestic openWeights />);
  const container = screen.getByRole("radiogroup", {
    name: "榜单维度",
  }).parentElement!;
  expect(container.classList.contains("overflow-x-auto")).toBe(true);
  expect(container.classList.contains("hide-scrollbar")).toBe(true);
  fireEvent.click(screen.getByRole("radio", { name: "编程" }));
  expect(push).toHaveBeenCalledWith(
    "/leaderboard/category/coding?domestic=true&open_weights=true",
  );
  expect(
    screen.getByRole("form", { name: "模型筛选" }).getAttribute("action"),
  ).toBe("/leaderboard");
  expect(
    screen.getByRole("link", { name: "清除筛选" }).getAttribute("href"),
  ).toBe("/leaderboard");
});

it("keeps the active dimension selected when it is clicked again", () => {
  render(<BoardFilters board="coding" domestic={false} openWeights={false} />);
  fireEvent.click(screen.getByRole("radio", { name: "编程" }));
  expect(push).not.toHaveBeenCalled();
  expect(
    screen.getByRole("radio", { name: "编程" }).getAttribute("aria-checked"),
  ).toBe("true");
});

it("synchronizes the checkboxes when the applied URL changes", () => {
  const { rerender } = render(
    <BoardFilters board="overall" domestic openWeights />,
  );
  rerender(
    <BoardFilters board="overall" domestic={false} openWeights={false} />,
  );
  expect(
    screen
      .getByRole("checkbox", { name: "国内模型" })
      .getAttribute("aria-checked"),
  ).toBe("false");
  expect(
    screen
      .getByRole("checkbox", { name: "开放权重" })
      .getAttribute("aria-checked"),
  ).toBe("false");
});

it("allows keyboard focus to move between dimensions", async () => {
  render(<BoardFilters board="overall" domestic={false} openWeights={false} />);
  const overall = screen.getByRole("radio", { name: "综合" });
  overall.focus();
  fireEvent.keyDown(overall, { key: "ArrowRight" });
  await waitFor(() =>
    expect(document.activeElement).toBe(
      screen.getByRole("radio", { name: "编程" }),
    ),
  );
});
