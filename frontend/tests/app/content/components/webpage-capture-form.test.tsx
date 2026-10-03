// @vitest-environment happy-dom

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ create: vi.fn(), push: vi.fn() }));
const toasts = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock("@/api/caijirenwu", () => ({ createCollectionJob: api.create }));
vi.mock("sonner", () => ({ toast: toasts }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
import { ApiRequestError } from "@/request";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: api.push, replace: vi.fn() }),
}));

import {
  resolvePendingOperation,
  validateWebPageTarget,
  WebPageCaptureForm,
} from "@/app/content/components/webpage-capture-form";

describe("webpage capture form", () => {
  it("renders one focused URL action without exposing collector controls", () => {
    const html = renderToStaticMarkup(createElement(WebPageCaptureForm));

    expect(html).toContain("添加网页");
    expect(html).toContain('type="url"');
    expect(html).toContain("创建任务");
    expect(html).not.toContain("Firecrawl");
    expect(html).not.toContain("脚本");
    expect(html).not.toContain("引擎");
  });

  it.each([
    ["", "请输入要采集的网页地址。"],
    ["example.com", "请输入完整的 http:// 或 https:// 地址。"],
    ["file:///tmp/example", "请输入完整的 http:// 或 https:// 地址。"],
    ["https://name:value@example.com", "网页地址不能包含用户名或密码。"],
    ["https://example.com/article", null],
    ["http://example.com", null],
  ])("validates the public URL shape for %s", (target, expected) => {
    expect(validateWebPageTarget(target)).toBe(expected);
  });

  it("reuses the operation ID only for a retry of the same target", () => {
    const createId = vi
      .fn<() => string>()
      .mockReturnValueOnce("operation-1")
      .mockReturnValueOnce("operation-2");

    const first = resolvePendingOperation(
      null,
      "https://example.com/a",
      createId,
    );
    const retry = resolvePendingOperation(
      first,
      "https://example.com/a",
      createId,
    );
    const changed = resolvePendingOperation(
      retry,
      "https://example.com/b",
      createId,
    );

    expect(retry).toBe(first);
    expect(changed.operationId).toBe("operation-2");
    expect(createId).toHaveBeenCalledTimes(2);
  });
});

describe("webpage capture feedback", () => {
  it("toasts validation and focuses the invalid URL without adding an error footer", () => {
    render(<WebPageCaptureForm />);
    fireEvent.click(screen.getByRole("button", { name: "创建任务" }));
    expect(toasts.error).toHaveBeenCalledWith("请输入要采集的网页地址。");
    expect(document.activeElement).toBe(screen.getByLabelText("网页地址"));
    expect(screen.getByLabelText("网页地址").getAttribute("aria-invalid")).toBe(
      "true",
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(api.create).not.toHaveBeenCalled();
  });

  it("preserves the URL and operation ID when a submission fails", async () => {
    api.create
      .mockRejectedValueOnce(
        new ApiRequestError({
          kind: "http",
          status: 503,
          message: "受理暂不可用",
          requestId: "capture-request",
        }),
      )
      .mockResolvedValueOnce({ job_id: "saved-job" });
    render(<WebPageCaptureForm />);
    fireEvent.change(screen.getByLabelText("网页地址"), {
      target: { value: "https://example.com/article" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建任务" }));
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith("受理暂不可用", {
        description: "请求编号：capture-request",
      }),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect((screen.getByLabelText("网页地址") as HTMLInputElement).value).toBe(
      "https://example.com/article",
    );
    fireEvent.click(screen.getByRole("button", { name: "创建任务" }));
    await waitFor(() =>
      expect(api.push).toHaveBeenCalledWith("/jobs/saved-job"),
    );
    expect(api.create.mock.calls[1][0].operation_id).toBe(
      api.create.mock.calls[0][0].operation_id,
    );
  });

  it("does not toast a late submission failure after unmount", async () => {
    let reject!: (error: unknown) => void;
    api.create.mockImplementationOnce(
      () =>
        new Promise((_, fail) => {
          reject = fail;
        }),
    );
    const view = render(<WebPageCaptureForm />);
    fireEvent.change(screen.getByLabelText("网页地址"), {
      target: { value: "https://example.com/article" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建任务" }));
    view.unmount();
    await act(async () =>
      reject(new ApiRequestError({ kind: "network", message: "晚到故障" })),
    );
    expect(toasts.error).not.toHaveBeenCalled();
    expect(api.push).not.toHaveBeenCalled();
  });
});
