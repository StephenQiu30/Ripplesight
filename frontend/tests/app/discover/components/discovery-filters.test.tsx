// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DiscoveryFilters } from "@/app/discover/components/discovery-filters";
import { selectOption } from "../../../select";
const scroller = vi.hoisted(() => ({
  current: { scrollTop: 0, scrollTo: vi.fn() },
}));
vi.mock("@/layout/basic-layout", () => ({
  useLayoutScrollContainer: () => scroller,
}));
beforeEach(() => {
  scroller.current.scrollTop = 0;
  scroller.current.scrollTo.mockImplementation((options: ScrollToOptions) => {
    scroller.current.scrollTop = options.top ?? 0;
  });
});
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

it("resets the content scroller when the result cursor changes, preserving an unchanged scope", () => {
  const view = render(<DiscoveryFilters {...props} params={{ q: "研究" }} />);
  scroller.current.scrollTop = 800;
  view.rerender(<DiscoveryFilters {...props} params={{ q: "研究" }} />);
  expect(scroller.current.scrollTop).toBe(800);
  view.rerender(
    <DiscoveryFilters {...props} params={{ q: "研究", cursor: "next" }} />,
  );
  expect(scroller.current.scrollTop).toBe(0);
  scroller.current.scrollTop = 400;
  view.rerender(
    <DiscoveryFilters {...props} params={{ q: "研究", window: "24h" }} />,
  );
  expect(scroller.current.scrollTop).toBe(0);
});
