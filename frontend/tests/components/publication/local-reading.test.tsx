// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const notifications = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications }));
import { SavedItems } from "@/components/publication/local-reading";
import { SAVED_KEY } from "@/components/publication/local-state";
const api = vi.hoisted(() => ({ read: vi.fn() }));
vi.mock("@/api/gongkaifabu", () => ({ getSitePublicationItem: api.read }));
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.resetAllMocks();
});
const id = (i: number) =>
  `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`;
it("keeps unreadable saved IDs removable and clamps pagination after cross-tab removal", async () => {
  localStorage.setItem(
    SAVED_KEY,
    JSON.stringify(Array.from({ length: 21 }, (_, i) => id(i + 1))),
  );
  api.read.mockRejectedValue(new Error("withdrawn"));
  render(<SavedItems full />);
  await screen.findByText(`暂时不可读取 · ${id(1)}`);
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  await screen.findByText(`暂时不可读取 · ${id(21)}`);
  localStorage.setItem(SAVED_KEY, JSON.stringify([id(1)]));
  fireEvent(window, new Event("storage"));
  await screen.findByText(`暂时不可读取 · ${id(1)}`);
  await waitFor(() => expect(screen.getByText("第 1 / 1 页")).toBeTruthy());
  fireEvent.click(screen.getByRole("button", { name: "移除" }));
  await screen.findByText("还没有收藏。");
  expect(JSON.parse(localStorage.getItem(SAVED_KEY)!)).toEqual([]);
});
it("reports corrupted stored JSON and preserves the raw bytes for explicit export", async () => {
  localStorage.setItem(SAVED_KEY, "broken JSON");
  render(<SavedItems full />);
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith(
      expect.stringContaining("原始数据保留"),
    ),
  );
  expect(screen.queryByText(/原始数据保留/)).toBeNull();
  fireEvent(window, new Event("storage"));
  await waitFor(() =>
    expect(screen.queryByText("正在读取当前公开材料…")).toBeNull(),
  );
  expect(notifications.error).toHaveBeenCalledOnce();
  expect(localStorage.getItem(SAVED_KEY)).toBe("broken JSON");
  expect(screen.getByRole("button", { name: "导出原始数据" })).toBeTruthy();
  expect(api.read).not.toHaveBeenCalled();
});
