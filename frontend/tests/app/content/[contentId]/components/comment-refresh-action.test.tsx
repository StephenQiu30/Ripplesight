// @vitest-environment happy-dom

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({
  readiness: vi.fn(),
  run: vi.fn(),
  push: vi.fn(),
}));
const toasts = vi.hoisted(() => ({ error: vi.fn() }));
vi.mock("@/api/zuopinziliao", () => ({
  getContentCommentRunReadiness: api.readiness,
  runContentComments: api.run,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push }) }));
vi.mock("sonner", () => ({ toast: toasts }));
import { ApiRequestError } from "@/request";
import { CommentRefreshAction } from "@/app/content/[contentId]/components/comment-refresh-action";
beforeEach(() =>
  api.readiness.mockResolvedValue({
    supported: true,
    available: true,
    reason: null,
  }),
);
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

describe("comment refresh feedback", () => {
  it("toasts an unconfirmed request and retries with the same operation ID", async () => {
    api.run
      .mockRejectedValueOnce(
        new ApiRequestError({ kind: "network", message: "无法连接服务" }),
      )
      .mockResolvedValueOnce({ job_id: "accepted-job" });
    render(<CommentRefreshAction postId="post-one" />);
    fireEvent.click(await screen.findByRole("button", { name: "更新评论" }));
    await waitFor(() =>
      expect(toasts.error).toHaveBeenCalledWith(
        "无法连接服务。可使用同一次操作标识重试。",
      ),
    );
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText("无法连接服务")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "更新评论" }));
    await waitFor(() =>
      expect(api.push).toHaveBeenCalledWith("/jobs/accepted-job"),
    );
    expect(api.run.mock.calls[1][1].operation_id).toBe(
      api.run.mock.calls[0][1].operation_id,
    );
  });

  it.each(["unmount", "post change"])(
    "ignores a late rejected write after %s",
    async (change) => {
      let reject!: (error: unknown) => void;
      api.run.mockImplementationOnce(
        () =>
          new Promise((_, fail) => {
            reject = fail;
          }),
      );
      const view = render(<CommentRefreshAction postId="post-one" />);
      fireEvent.click(await screen.findByRole("button", { name: "更新评论" }));
      if (change === "unmount") view.unmount();
      else view.rerender(<CommentRefreshAction postId="post-two" />);
      await act(async () =>
        reject(new ApiRequestError({ kind: "network", message: "晚到故障" })),
      );
      expect(toasts.error).not.toHaveBeenCalled();
      expect(api.push).not.toHaveBeenCalled();
    },
  );

  it("does not navigate after an accepted write resolves on an abandoned page", async () => {
    let resolve!: (value: { job_id: string }) => void;
    api.run.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    const view = render(<CommentRefreshAction postId="post-one" />);
    fireEvent.click(await screen.findByRole("button", { name: "更新评论" }));
    view.unmount();
    await act(async () => resolve({ job_id: "accepted-job" }));
    expect(api.push).not.toHaveBeenCalled();
    expect(toasts.error).not.toHaveBeenCalled();
  });
});
