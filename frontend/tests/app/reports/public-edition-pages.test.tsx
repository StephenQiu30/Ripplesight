// @vitest-environment happy-dom
import { expectOnePageHeading } from "../../page-heading";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import ReportPage, { generateMetadata } from "@/app/reports/[reportId]/page";
import EditionPage from "@/app/reports/[reportId]/[key]/page";
import ArchivePage from "@/app/reports/[reportId]/archive/page";
import Loading from "@/app/reports/[reportId]/loading";
import ArchiveLoading from "@/app/reports/[reportId]/archive/loading";
import NotFound from "@/app/reports/[reportId]/not-found";
import ErrorBoundary from "@/app/reports/[reportId]/error";
import { ApiRequestError } from "@/request";
import { edition, editionEntry } from "./edition-fixtures";

const api = vi.hoisted(() => ({
  edition: vi.fn(),
  catalogue: vi.fn(),
  navigation: vi.fn(),
  calendar: vi.fn(),
  connection: vi.fn(),
  privateDetail: vi.fn(),
}));
vi.mock("next/server", () => ({ connection: api.connection }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));
vi.mock("@/api/gongkaifabu", () => ({ getPublicEdition: api.edition }));
vi.mock("@/api/gongkaikanwumulu", () => ({
  listPublicEditionCatalogue: api.catalogue,
  getPublicEditionNavigation: api.navigation,
  getPublicDailyCalendar: api.calendar,
}));
vi.mock("@/app/reports/[reportId]/components/report-detail", () => ({
  ReportDetail: api.privateDetail,
}));

const params = (reportId = "daily") => ({
  params: Promise.resolve({ reportId }),
});
beforeEach(() => {
  vi.resetAllMocks();
  api.edition.mockResolvedValue(edition);
  api.catalogue.mockResolvedValue({
    kind: "daily",
    entries: [editionEntry(edition.key), editionEntry("2026-10-05")],
    next_before_key: null,
  });
  api.navigation.mockResolvedValue({
    current: editionEntry(edition.key),
    previous: editionEntry("2026-10-05"),
    next: null,
  });
  api.calendar.mockResolvedValue({
    month: "2026-10",
    entries: [editionEntry(edition.key)],
  });
});
afterEach(() => {
  if (document.body.textContent) expectOnePageHeading();
  cleanup();
});

it("reads the latest true edition and catalogue without a session dependency", async () => {
  render(await ReportPage(params()));
  expect(
    screen.getByRole("heading", { name: edition.title, level: 1 }),
  ).toBeTruthy();
  expect(api.catalogue).toHaveBeenCalledWith({ kind: "daily", limit: 6 });
  expect(api.edition).toHaveBeenCalledWith({ kind: "daily", key: edition.key });
  expect(api.connection).toHaveBeenCalledOnce();
  expect(screen.getByRole("link", { name: /刊物 2026-10-05/ })).toBeTruthy();
});

it("shows a real unpublished empty state without requesting a nonexistent edition", async () => {
  api.catalogue.mockResolvedValue({
    kind: "daily",
    entries: [],
    next_before_key: null,
  });
  render(await ReportPage(params()));
  expect(screen.getByRole("status", { name: "暂无刊物" })).toBeTruthy();
  expect(
    screen.getByRole("link", { name: "读取刊物历史" }).getAttribute("href"),
  ).toBe("/reports/daily/archive");
  expect(api.edition).not.toHaveBeenCalled();
  expect(api.navigation).not.toHaveBeenCalled();
});

it("keeps content available when the latest navigation request fails", async () => {
  api.navigation.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status: 503,
      code: "navigation_unavailable",
      message: "internal",
    }),
  );
  render(await ReportPage(params()));
  expect(
    screen.getByRole("heading", { name: edition.title, level: 1 }),
  ).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toContain(
    "navigation_unavailable · 503",
  );
});

it("loads the exact archived issue and past catalogue before its key without silently changing dates", async () => {
  render(
    await EditionPage({
      params: Promise.resolve({ reportId: "daily", key: edition.key }),
    }),
  );
  expect(api.edition).toHaveBeenCalledWith({ kind: "daily", key: edition.key });
  expect(api.catalogue).toHaveBeenCalledWith({
    kind: "daily",
    before_key: edition.key,
    limit: 5,
  });
  expect(
    screen.getByRole("heading", { name: edition.title, level: 1 }),
  ).toBeTruthy();
});

it("keeps the archived body when catalogue loading fails", async () => {
  api.catalogue.mockRejectedValue(
    new ApiRequestError({
      kind: "network",
      code: "catalogue_offline",
      message: "internal",
    }),
  );
  render(
    await EditionPage({
      params: Promise.resolve({ reportId: "daily", key: edition.key }),
    }),
  );
  expect(
    screen.getByRole("heading", { name: edition.title, level: 1 }),
  ).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toContain("catalogue_offline");
});

it("keeps missing or withdrawn archived issues in the existing not-found branch", async () => {
  api.edition.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status: 404,
      code: "edition_not_found",
      message: "withdrawn",
    }),
  );
  await expect(
    EditionPage({
      params: Promise.resolve({ reportId: "daily", key: edition.key }),
    }),
  ).rejects.toThrow("NEXT_NOT_FOUND");
  render(<NotFound />);
  expect(
    screen.getByRole("heading", { name: "这份刊物目前不可公开阅读" }),
  ).toBeTruthy();
  expect(screen.getByText(/已撤回或许可已经变化/)).toBeTruthy();
});

it.each([401, 403])(
  "handles an unexpected public %s denial without making login a reading prerequisite",
  async (status) => {
    api.catalogue.mockRejectedValue(
      new ApiRequestError({
        kind: "http",
        status,
        code: "public_read_denied",
        message: "sensitive",
      }),
    );
    render(await ReportPage(params()));
    expect(
      screen.getByRole("status", { name: "这份刊物目前不可公开阅读" }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "公开刊物无需登录。请稍后重新读取，或返回首页查看其他公开内容。",
      ),
    ).toBeTruthy();
    expect(screen.getByText(`public_read_denied · ${status}`)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "登录" })).toBeNull();
  },
);

it("shows safe PageState error details for a publication outage", async () => {
  api.catalogue.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status: 503,
      code: "publication_not_configured",
      message: "sensitive",
    }),
  );
  render(await ReportPage(params()));
  expect(screen.getByRole("alert").textContent).toContain(
    "publication_not_configured · 503",
  );
  expect(screen.getByRole("link", { name: "重新读取" })).toBeTruthy();
  expect(screen.queryByText("sensitive")).toBeNull();
});

it("preserves the personal ReportDetail and noindex contract without requesting public editions", async () => {
  const page = await ReportPage(params("private-report-id"));
  expect(page.type).toBe(api.privateDetail);
  expect(page.props).toEqual({ reportId: "private-report-id" });
  expect(await generateMetadata(params("private-report-id"))).toEqual({
    title: "个人报告详情",
    robots: { index: false, follow: false },
  });
  expect(api.edition).not.toHaveBeenCalled();
  expect(api.catalogue).not.toHaveBeenCalled();
});

it("keeps the archive catalogue when its optional calendar fails and exposes a retryable month", async () => {
  api.calendar.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status: 503,
      code: "calendar_unavailable",
      message: "sensitive",
    }),
  );
  render(await ArchivePage(params()));
  expect(
    screen.getByRole("link", { name: `刊物 ${edition.key}` }),
  ).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toContain(
    "calendar_unavailable · 503",
  );
  expect((screen.getByLabelText("日报月份") as HTMLInputElement).value).toBe(
    "2026-10",
  );
  expect(
    (screen.getByRole("button", { name: "读取月份" }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
});

it("shows an archive request failure with its code", async () => {
  api.catalogue.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status: 503,
      code: "catalogue_unavailable",
      message: "private",
    }),
  );
  render(await ArchivePage(params()));
  expect(screen.getByRole("alert").textContent).toContain(
    "catalogue_unavailable · 503",
  );
});

it("provides reading and archive loading states with accessible status semantics", () => {
  const { unmount } = render(<Loading />);
  expect(
    screen
      .getByRole("status", { name: "正在读取报告内容" })
      .getAttribute("aria-busy"),
  ).toBe("true");
  unmount();
  render(<ArchiveLoading />);
  expect(
    screen
      .getByRole("status", { name: "正在读取刊物历史" })
      .getAttribute("aria-busy"),
  ).toBe("true");
});

it("offers a scoped render-error retry while omitting the underlying exception message", () => {
  const reset = vi.fn();
  render(
    <ErrorBoundary
      error={Object.assign(new Error("sensitive"), { digest: "safe-digest" })}
      reset={reset}
    />,
  );
  expect(screen.getByRole("alert").textContent).toContain("safe-digest");
  expect(screen.queryByText("sensitive")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  expect(reset).toHaveBeenCalledOnce();
});
