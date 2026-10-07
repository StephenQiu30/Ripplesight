// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { publicStory } from "../../components/home-fixtures";
import { ApiRequestError } from "@/request";
const api = vi.hoisted(() => ({ hot: vi.fn() }));
vi.mock("next/server", () => ({ connection: vi.fn() }));
vi.mock("@/api/gongkaifabu", () => ({ getPublicHotStories: api.hot }));
import StoriesPage from "@/app/discover/stories/page";
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
it("links published events through the anonymous public reading route", async () => {
  api.hot.mockResolvedValue({ stories: [publicStory] });
  render(await StoriesPage());
  expect(api.hot).toHaveBeenCalledWith({ limit: 20 });
  expect(
    screen.getByRole("link", { name: publicStory.title }).getAttribute("href"),
  ).toBe("/discover/stories/story-1");
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("事件");
});
it("keeps an empty event index separate from API failure", async () => {
  api.hot.mockResolvedValue({ stories: [] });
  render(await StoriesPage());
  expect(screen.getByRole("heading", { name: "暂无公开事件" })).toBeTruthy();
  cleanup();
  api.hot.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status: 503,
      code: "publication_search_busy",
      message: "unavailable",
    }),
  );
  render(await StoriesPage());
  expect(screen.queryByRole("heading", { name: "暂无公开事件" })).toBeNull();
  expect(screen.getByText(/publication_search_busy/)).toBeTruthy();
});
