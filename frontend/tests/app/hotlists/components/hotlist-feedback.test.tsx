// @vitest-environment happy-dom

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ sources: vi.fn(), toastError: vi.fn() }));
vi.mock("@/api/rebang", () => ({
  listHotlistSources: mocks.sources,
  listHotlistSnapshots: vi.fn(),
  getHistoricalHotlistSnapshot: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: mocks.toastError } }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { HotlistWorkspace } from "@/app/hotlists/components/hotlist-workspace";
import { ApiRequestError } from "@/request";

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("sends the source failure and request ID to Sonner while keeping a native recovery action", async () => {
  mocks.sources.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status: 503,
      message: "来源读取失败",
      requestId: "request-check",
    }),
  );
  render(<HotlistWorkspace />);
  await waitFor(() =>
    expect(mocks.toastError).toHaveBeenCalledExactlyOnceWith("来源读取失败", {
      description: "请求编号：request-check",
    }),
  );
  expect(screen.queryByText("来源读取失败")).toBeNull();
  expect(screen.getByRole("button", { name: "重新加载" })).toBeTruthy();
});

it("ignores a source failure that arrives after leaving the page", async () => {
  let reject!: (failure: Error) => void;
  mocks.sources.mockReturnValue(
    new Promise((_resolve, fail) => {
      reject = fail;
    }),
  );
  const view = render(<HotlistWorkspace />);
  const signal = mocks.sources.mock.calls[0][0].signal as AbortSignal;
  view.unmount();
  expect(signal.aborted).toBe(true);
  await act(async () => {
    reject(new Error("late failure"));
  });
  expect(mocks.toastError).not.toHaveBeenCalled();
});
