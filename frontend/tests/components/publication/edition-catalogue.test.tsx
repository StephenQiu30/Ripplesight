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
import { PublicEditionCatalogue } from "@/components/publication/edition-catalogue";
const api = vi.hoisted(() => ({ catalogue: vi.fn(), calendar: vi.fn() }));
vi.mock("@/api/gongkaikanwumulu", () => ({
  listPublicEditionCatalogue: api.catalogue,
  getPublicDailyCalendar: api.calendar,
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
const entry = (key: string): HotKeyAPI.PublicEditionIndexView => ({
  key,
  kind: "daily",
  title: `日报 ${key}`,
  revision: 2,
  created_at: "2026-10-02T00:00:00Z",
  reading_url: `/reports/daily/${key}`,
});
it("links only true current calendar days and continues history using the server cursor", async () => {
  api.catalogue.mockResolvedValue({
    kind: "daily",
    entries: [entry("2026-09-30")],
    next_before_key: null,
  });
  render(
    <PublicEditionCatalogue
      initial={{
        kind: "daily",
        entries: [entry("2026-10-01")],
        next_before_key: "2026-10-01",
      }}
      initialCalendar={{ month: "2026-10", entries: [entry("2026-10-01")] }}
    />,
  );
  expect(
    screen.getByRole("link", { name: "2026-10-01 日报：日报 2026-10-01" }),
  ).toBeTruthy();
  expect(screen.queryByRole("link", { name: /^2026-10-02 日报/ })).toBeNull();
  expect(screen.getByLabelText("2026-10-02 暂无公开日报")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "更早刊期" }));
  await screen.findByRole("link", { name: "日报 2026-09-30" });
  expect(api.catalogue).toHaveBeenCalledWith({
    kind: "daily",
    before_key: "2026-10-01",
    limit: 20,
  });
  expect(screen.queryByRole("button", { name: "更早刊期" })).toBeNull();
});
it("removes the old calendar when a changed month cannot be read", async () => {
  api.calendar.mockRejectedValue(new Error("withdrawn"));
  render(
    <PublicEditionCatalogue
      initial={{ kind: "daily", entries: [], next_before_key: null }}
      initialCalendar={{ month: "2026-10", entries: [entry("2026-10-01")] }}
    />,
  );
  fireEvent.change(screen.getByLabelText("日报月份"), {
    target: { value: "2026-09" },
  });
  fireEvent.click(screen.getByRole("button", { name: "读取月份" }));
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith(
      "暂时无法读取月份日历，请检查月份或重试。",
    ),
  );
  expect(screen.queryByText(/暂时无法读取月份日历/)).toBeNull();
  expect(
    screen.queryByRole("link", { name: "2026-10-01 日报：日报 2026-10-01" }),
  ).toBeNull();
});
