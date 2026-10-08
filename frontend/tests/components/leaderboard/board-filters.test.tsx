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

it("uses the design dimensions, maps open weights to the real filter and labels unavailable context", () => {
  render(<BoardFilters board="overall" domestic openWeights />);
  fireEvent.click(screen.getByRole("radio", { name: "编程" }));
  expect(push).toHaveBeenCalledWith(
    "/leaderboard/category/coding?domestic=true",
  );
  expect(
    screen.getByRole("radio", { name: "长上下文" }).hasAttribute("disabled"),
  ).toBe(true);
  expect(screen.queryByRole("form", { name: "模型筛选" })).toBeNull();
});
it("keeps the active dimension selected when it is clicked again", () => {
  render(<BoardFilters board="coding" domestic={false} openWeights={false} />);
  fireEvent.click(screen.getByRole("radio", { name: "编程" }));
  expect(push).not.toHaveBeenCalled();
  expect(
    screen.getByRole("radio", { name: "编程" }).getAttribute("aria-checked"),
  ).toBe("true");
});

it("synchronizes the active open-weight dimension from URL props", () => {
  const { rerender } = render(
    <BoardFilters board="overall" domestic={false} openWeights />,
  );
  expect(
    screen.getByRole("radio", { name: "开源" }).getAttribute("aria-checked"),
  ).toBe("true");
  rerender(
    <BoardFilters board="overall" domestic={false} openWeights={false} />,
  );
  expect(
    screen.getByRole("radio", { name: "综合" }).getAttribute("aria-checked"),
  ).toBe("true");
  fireEvent.click(screen.getByRole("radio", { name: "开源" }));
  expect(push).toHaveBeenCalledWith("/leaderboard?open_weights=true");
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
