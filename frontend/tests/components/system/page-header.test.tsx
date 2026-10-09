// @vitest-environment happy-dom

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { PageHeader } from "@/components/system/page-header";
import { Button } from "@/components/ui/button";

afterEach(cleanup);

it("keeps one page title and exposes the detail path and page action", () => {
  render(
    <PageHeader
      title="模型证据"
      titleId="model-title"
      description="查看公开评测"
      breadcrumbs={[
        { label: "模型榜", href: "/leaderboard" },
        { label: "模型证据" },
      ]}
      actions={<Button>查看来源</Button>}
    />,
  );
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  expect(screen.getByRole("heading").id).toBe("model-title");
  const path = screen.getByRole("navigation", { name: "面包屑" });
  expect(
    within(path).getByRole("link", { name: "模型榜" }).getAttribute("href"),
  ).toBe("/leaderboard");
  expect(within(path).getByText("模型证据").getAttribute("aria-current")).toBe(
    "page",
  );
  expect(screen.getByRole("button", { name: "查看来源" })).toBeTruthy();
});

it("allows a first-level page to show only its title", () => {
  render(<PageHeader title="探索" />);
  expect(screen.getByRole("heading", { name: "探索", level: 1 })).toBeTruthy();
  expect(screen.queryByRole("navigation")).toBeNull();
  expect(screen.queryByRole("link")).toBeNull();
});
