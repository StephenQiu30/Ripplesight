// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ChromeConnection } from "@/app/sources/components/chrome-connection";
import { connectBilibiliChrome } from "@/api/laiyuannengli";

vi.mock("@/api/laiyuannengli", () => ({ connectBilibiliChrome: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("activates through the authenticated generated client before offering topic creation", async () => {
  vi.mocked(connectBilibiliChrome).mockResolvedValue({
    source_key: "bilibili",
    connection_id: "id",
    connection_version: 1,
    capabilities: ["search", "comments"],
  });
  const refresh = vi.fn().mockResolvedValue(undefined);
  render(<ChromeConnection onConnected={refresh} />);
  expect(screen.queryByRole("link", { name: "创建监控主题" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "启用 Chrome 采集" }));
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  expect(connectBilibiliChrome).toHaveBeenCalledOnce();
  expect(
    screen.getByRole("link", { name: "创建监控主题" }).getAttribute("href"),
  ).toBe("/monitors/new");
});

it("does not claim connected after a rejected request and allows retry", async () => {
  vi.mocked(connectBilibiliChrome).mockRejectedValue(new Error("failed"));
  render(<ChromeConnection onConnected={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "启用 Chrome 采集" }));
  await screen.findByText("启用失败，请重试。");
  expect(screen.queryByRole("link", { name: "创建监控主题" })).toBeNull();
  expect(
    screen
      .getByRole("button", { name: "启用 Chrome 采集" })
      .hasAttribute("disabled"),
  ).toBe(false);
});
