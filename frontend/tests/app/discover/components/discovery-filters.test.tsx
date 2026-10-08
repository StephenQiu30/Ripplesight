// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DiscoveryFilters } from "@/app/discover/components/discovery-filters";
import { selectOption } from "../../../select";
const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
const props = { mode: "all", window: "7d", by: "timeline", categories: [] };
it("submits query and preserved server scope while clearing the old cursor", () => {
  render(
    <DiscoveryFilters
      {...props}
      params={{ q: "研究", source_key: "rss", tag: "安全", cursor: "old" }}
    />,
  );
  const form = screen.getByRole("search") as HTMLFormElement;
  const data = new FormData(form);
  expect(form.getAttribute("action")).toBe("/discover");
  expect(data.get("q")).toBe("研究");
  expect(data.get("source_key")).toBe("rss");
  expect(data.get("cursor")).toBeNull();
  expect(screen.queryByText("高级筛选")).toBeNull();
});
it("routes type and time filters through URL scope without pretending sentiment is available", async () => {
  render(<DiscoveryFilters {...props} params={{ q: "模型", cursor: "old" }} />);
  fireEvent.click(screen.getByRole("radio", { name: "事件" }));
  expect(navigation.push).toHaveBeenCalledWith(
    "/discover?q=%E6%A8%A1%E5%9E%8B&type=events",
  );
  await selectOption(
    screen.getByRole("combobox", { name: "时间范围" }),
    "过去 24 小时",
  );
  expect(navigation.push).toHaveBeenCalledWith(
    "/discover?q=%E6%A8%A1%E5%9E%8B&window=24h",
  );
  expect(
    screen
      .getByRole("combobox", { name: "情感筛选暂不可用" })
      .hasAttribute("disabled"),
  ).toBe(true);
});
