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
import { ApiRequestError } from "@/request";
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
  expect(screen.getByRole("alert").textContent).toContain("月份日历暂不可用");
  expect(screen.getByRole("alert").textContent).toContain(
    "publication_read_failed",
  );
});

it.each(["weekly", "monthly"] as const)(
  "keeps an empty %s archive useful without a daily calendar",
  (kind) => {
    render(
      <PublicEditionCatalogue
        initial={{ kind, entries: [], next_before_key: null }}
      />,
    );
    expect(screen.getByText("暂无刊物")).toBeTruthy();
    expect(screen.queryByLabelText("日报月份")).toBeNull();
    expect(
      screen.getByRole("link", { name: /最新/ }).getAttribute("href"),
    ).toBe(`/reports/${kind}`);
    expect(
      screen.getByRole("link", { name: /^订阅/ }).getAttribute("href"),
    ).toBe(`/feed/${kind}.xml`);
  },
);

it("preserves the existing list and cursor after a failed page, marks it stale and allows a retry", async () => {
  api.catalogue
    .mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 503,
        code: "catalogue_busy",
        message: "internal",
      }),
    )
    .mockResolvedValueOnce({
      kind: "weekly",
      entries: [entry("2026-W39")],
      next_before_key: null,
    });
  render(
    <PublicEditionCatalogue
      initial={{
        kind: "weekly",
        entries: [entry("2026-W40")],
        next_before_key: "signed-key",
      }}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "更早刊期" }));
  await screen.findByText("已过期");
  expect(screen.getByRole("link", { name: "日报 2026-W40" })).toBeTruthy();
  expect(screen.getByRole("status").textContent).toContain(
    "catalogue_busy · 503",
  );
  fireEvent.click(screen.getByRole("button", { name: "重试更早刊期" }));
  await screen.findByRole("link", { name: "日报 2026-W39" });
  expect(api.catalogue).toHaveBeenNthCalledWith(2, {
    kind: "weekly",
    before_key: "signed-key",
    limit: 20,
  });
  expect(screen.queryByText("已过期")).toBeNull();
});

it("shows month loading, prevents duplicate actions, and only links returned days", async () => {
  let resolveMonth!: (value: HotKeyAPI.PublicDailyCalendarView) => void;
  api.calendar.mockImplementation(
    () =>
      new Promise<HotKeyAPI.PublicDailyCalendarView>((resolve) => {
        resolveMonth = resolve;
      }),
  );
  render(
    <PublicEditionCatalogue
      initial={{ kind: "daily", entries: [], next_before_key: null }}
      initialMonth="2026-10"
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "读取月份" }));
  expect(screen.getByRole("status", { name: "正在读取月份日历" })).toBeTruthy();
  expect(
    (screen.getByRole("button", { name: "正在读取月份…" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  resolveMonth({ month: "2026-10", entries: [entry("2026-10-01")] });
  await screen.findByRole("link", { name: "2026-10-01 日报：日报 2026-10-01" });
  expect(api.calendar).toHaveBeenCalledOnce();
  expect(api.calendar).toHaveBeenCalledWith({ month: "2026-10" });
  expect(screen.getByLabelText("2026-10-02 暂无公开日报")).toBeTruthy();
});
