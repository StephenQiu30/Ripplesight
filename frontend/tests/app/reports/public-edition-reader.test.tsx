// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { PublicEditionReader } from "@/app/reports/[reportId]/[key]/components/public-edition-reader";
import { EditionCopyLink } from "@/components/publication/edition-copy-link";
import { ApiRequestError } from "@/request";
import { edition, editionEntry } from "./edition-fixtures";

const notifications = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications }));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

it.each(["daily", "weekly", "monthly"] as const)(
  "renders %s sections and a matching anchor outline with only true past editions",
  (kind) => {
    const { container } = render(
      <PublicEditionReader
        edition={{ ...edition, kind }}
        catalogue={{
          kind,
          entries: [
            editionEntry("2026-10-07"),
            editionEntry(edition.key),
            editionEntry("2026-10-05"),
          ],
          next_before_key: null,
        }}
        navigation={{
          current: editionEntry(edition.key),
          previous: editionEntry("2026-10-05"),
          next: null,
        }}
      />,
    );
    const outline = within(
      screen.getByRole("navigation", { name: "本期目录" }),
    );
    const links = outline.getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual([
      "重点关注",
      "重点事件",
      "今日社媒热点",
      "固定引用",
    ]);
    for (const link of links) {
      const heading = container.querySelector(link.getAttribute("href")!);
      expect(heading?.tagName).toBe("H2");
      expect(heading?.textContent).toBe(link.textContent);
      expect(heading?.getAttribute("tabindex")).toBe("-1");
    }
    const table = screen.getByRole("table", { name: "今日社媒热点" });
    expect(table.getAttribute("tabindex")).toBe("0");
    expect(table.parentElement?.className).toContain("overflow-x-auto");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["序号", "资讯", "来源", "时间"]);
    expect(
      within(table)
        .getByRole("link", { name: edition.entries[0].title })
        .getAttribute("href"),
    ).toBe(edition.entries[0].reading_url);
    expect(screen.queryByRole("columnheader", { name: "帖子" })).toBeNull();
    expect(screen.queryByText("舆情提示")).toBeNull();
    expect(screen.queryByText("0 个来源")).toBeNull();
    const past = within(screen.getByRole("region", { name: "往期刊物" }));
    expect(
      past.getByRole("link", { name: /刊物 2026-10-05/ }).getAttribute("href"),
    ).toBe("/reports/daily/2026-10-05");
    expect(past.queryByText("刊物 2026-10-07")).toBeNull();
    expect(past.queryByText(`刊物 ${edition.key}`)).toBeNull();
    expect(
      screen.getByRole("link", { name: "读取 Markdown" }).getAttribute("href"),
    ).toBe(`/reports/${kind}/${edition.key}.md`);
    expect(
      container.querySelector("[data-edition-sidebar]")?.className,
    ).toContain("print:hidden");
    expect(
      screen.getByRole("navigation", { name: "刊期导航" }).className,
    ).toContain("print:hidden");
    expect(container.querySelector("[data-edition-references]")).toBeTruthy();
  },
);

it("keeps the body readable when past editions fail and transports safe error codes", () => {
  render(
    <PublicEditionReader
      edition={edition}
      catalogueError={
        new ApiRequestError({
          kind: "http",
          status: 503,
          code: "catalogue_unavailable",
          message: "private upstream details",
        })
      }
    />,
  );
  expect(
    screen.getByRole("heading", { level: 1, name: edition.title }),
  ).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toContain(
    "catalogue_unavailable · 503",
  );
  expect(screen.queryByText("private upstream details")).toBeNull();
  expect(screen.queryByText("暂无更早的公开刊物。")).toBeNull();
});

it("omits empty chapters and keeps a real empty issue readable", () => {
  render(
    <PublicEditionReader
      edition={{
        ...edition,
        entries: [],
        lead: "",
        themes: [],
        sections: [],
        highlights: [],
        flashes: [],
      }}
    />,
  );
  expect(screen.getByText("本期暂无可公开的条目。")).toBeTruthy();
  expect(screen.queryByRole("navigation", { name: "本期目录" })).toBeNull();
  expect(screen.queryByRole("heading", { name: "今日社媒热点" })).toBeNull();
});

it("labels a derived reference count accurately when publication metrics are missing", () => {
  render(<PublicEditionReader edition={{ ...edition, metrics: {} }} />);
  expect(
    screen.getByRole("article", { name: edition.title }).textContent,
  ).toContain("1 条固定引用");
  expect(screen.queryByText("条精选")).toBeNull();
  expect(screen.queryByText("个来源")).toBeNull();
});

it("uses the existing print action and keeps collapsed references printable without scroll clipping", () => {
  const print = vi.fn();
  vi.stubGlobal("print", print);
  render(<PublicEditionReader edition={edition} />);
  fireEvent.click(screen.getByRole("button", { name: "打印这份刊物" }));
  expect(print).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "全部 1 条固定引用" }));
  expect(screen.getByRole("table", { name: "固定引用" })).toBeTruthy();
  const css = readFileSync(
    "src/app/reports/[reportId]/[key]/components/public-edition-reader.module.css",
    "utf8",
  );
  expect(css).toContain("@media print");
  expect(css).toMatch(/\[data-edition-sidebar\]\s*\{\s*display: none/);
  expect(css).toMatch(
    /\[data-edition-references\][\s\S]*?display: block !important/,
  );
  expect(css).toMatch(
    /\[data-slot="table-container"\]\s*\{\s*overflow: visible/,
  );
  expect(css).toContain("min-width: 0");
  expect(css).toContain("overflow-wrap: anywhere");
});

it("copies the fixed edition URL from a latest-page entry and reports success with Sonner", async () => {
  const clipboard = vi
    .spyOn(navigator.clipboard, "writeText")
    .mockResolvedValue(undefined);
  render(<EditionCopyLink href="/reports/daily/2026-10-06" />);
  fireEvent.click(screen.getByRole("button", { name: "复制链接" }));
  await waitFor(() =>
    expect(notifications.success).toHaveBeenCalledWith("阅读链接已复制。"),
  );
  expect(clipboard).toHaveBeenCalledWith(
    new URL("/reports/daily/2026-10-06", window.location.origin).href,
  );
});

it("reports clipboard denial with Sonner and restores the action", async () => {
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(
    new Error("denied"),
  );
  render(<EditionCopyLink href="/reports/daily/2026-10-06" />);
  fireEvent.click(screen.getByRole("button", { name: "复制链接" }));
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith(
      "暂时无法复制，请复制浏览器地址。",
    ),
  );
  expect(
    (screen.getByRole("button", { name: "复制链接" }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
  expect(screen.queryByText("暂时无法复制，请复制浏览器地址。")).toBeNull();
});
