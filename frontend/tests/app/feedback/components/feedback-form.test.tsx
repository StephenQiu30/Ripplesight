// @vitest-environment happy-dom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({
  submit: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));
vi.mock("sonner", () => ({
  toast: { error: api.toastError, success: api.toastSuccess },
}));
vi.mock("@/api/fankui", () => ({ submitFeedback: api.submit }));
import { FeedbackForm } from "@/app/feedback/components/feedback-form";
import { ApiRequestError } from "@/request";
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
it("retains the operation identity after an uncertain response and clears it after success", async () => {
  api.submit
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ id: "f", status: "new" });
  render(<FeedbackForm />);
  fireEvent.change(screen.getByLabelText("反馈内容"), {
    target: { value: "阅读页面缺失正文" },
  });
  fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));
  await waitFor(() =>
    expect(api.toastError).toHaveBeenCalledWith(
      "反馈提交失败，请保留当前内容后重试。",
    ),
  );
  expect(screen.queryByText("反馈提交失败，请保留当前内容后重试。")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));
  await waitFor(() =>
    expect(api.toastSuccess).toHaveBeenCalledWith("反馈已保存，编号 f。"),
  );
  expect(api.submit.mock.calls[0][0].operation_id).toBe(
    api.submit.mock.calls[1][0].operation_id,
  );
  await waitFor(() =>
    expect(
      (screen.getByLabelText("反馈内容") as HTMLTextAreaElement).value,
    ).toBe(""),
  );
});

it.each(["success", "failure"])(
  "ignores a late feedback %s after leaving the page",
  async (outcome) => {
    let resolve!: (result: object) => void;
    let reject!: (failure: Error) => void;
    api.submit.mockReturnValue(
      new Promise((done, fail) => {
        resolve = done;
        reject = fail;
      }),
    );
    const view = render(<FeedbackForm />);
    fireEvent.change(screen.getByLabelText("反馈内容"), {
      target: { value: "测试反馈" },
    });
    fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));
    await waitFor(() => expect(api.submit).toHaveBeenCalled());
    view.unmount();
    await act(async () => {
      if (outcome === "success") resolve({ id: "late" });
      else reject(new Error("late"));
    });
    expect(api.toastError).not.toHaveBeenCalled();
    expect(api.toastSuccess).not.toHaveBeenCalled();
  },
);

it("does not report a cancelled feedback request as an error", async () => {
  api.submit.mockRejectedValue(
    new ApiRequestError({ kind: "cancelled", message: "cancelled" }),
  );
  render(<FeedbackForm />);
  fireEvent.change(screen.getByLabelText("反馈内容"), {
    target: { value: "测试反馈" },
  });
  fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));
  await waitFor(() => expect(api.submit).toHaveBeenCalledTimes(1));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "提交反馈" })).toHaveProperty(
      "disabled",
      false,
    ),
  );
  expect(api.toastError).not.toHaveBeenCalled();
  expect(api.toastSuccess).not.toHaveBeenCalled();
});
