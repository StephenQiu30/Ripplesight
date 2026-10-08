// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SavedNote, readSavedNotes } from "@/components/publication/saved-note";
import {
  SAVED_KEY,
  NOTES_KEY,
  clearLocalReading,
} from "@/components/publication/local-state";
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
const id = "00000000-0000-4000-8000-000000000001";
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.clearAllMocks();
});
it("persists user notes across remounts without copying a publication body", async () => {
  localStorage.setItem(SAVED_KEY, JSON.stringify([id]));
  const view = render(<SavedNote id={id} />);
  fireEvent.click(screen.getByRole("button", { name: "添加备注" }));
  fireEvent.change(screen.getByRole("textbox", { name: "备注" }), {
    target: { value: "关注下一次更新" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存备注" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(readSavedNotes(localStorage)).toEqual({ [id]: "关注下一次更新" });
  view.unmount();
  render(<SavedNote id={id} />);
  expect(await screen.findByText("关注下一次更新")).toBeTruthy();
  await clearLocalReading();
  expect(localStorage.getItem(NOTES_KEY)).toBeNull();
});
it("preserves corrupt note storage instead of overwriting it", async () => {
  localStorage.setItem(SAVED_KEY, JSON.stringify([id]));
  localStorage.setItem(NOTES_KEY, "broken");
  render(<SavedNote id={id} />);
  fireEvent.click(screen.getByRole("button", { name: "添加备注" }));
  fireEvent.change(screen.getByRole("textbox", { name: "备注" }), {
    target: { value: "新的备注" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存备注" }));
  await waitFor(() => expect(toast.error).toHaveBeenCalled());
  expect(localStorage.getItem(NOTES_KEY)).toBe("broken");
  expect(screen.getByRole("dialog")).toBeTruthy();
});
it("refuses notes for a bookmark removed in another tab", async () => {
  render(<SavedNote id={id} />);
  fireEvent.click(screen.getByRole("button", { name: "添加备注" }));
  fireEvent.change(screen.getByRole("textbox", { name: "备注" }), {
    target: { value: "备注" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存备注" }));
  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith("请先收藏这条资讯。"),
  );
  expect(localStorage.getItem(NOTES_KEY)).toBeNull();
});
it("rejects oversized and invalid persisted records", () => {
  expect(() =>
    readSavedNotes({
      getItem: () => JSON.stringify({ [id]: "x".repeat(2001) }),
    }),
  ).toThrow();
  expect(() =>
    readSavedNotes({ getItem: () => JSON.stringify({ invalid: "note" }) }),
  ).toThrow();
});
