// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ submit: vi.fn() }));
vi.mock("@/api/fankui", () => ({ submitFeedback: api.submit }));
import { FeedbackForm } from "@/app/feedback/components/feedback-form";
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
  await screen.findByText("反馈提交失败，请保留当前内容后重试。");
  fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));
  await screen.findByText("反馈已保存，编号 f。");
  expect(api.submit.mock.calls[0][0].operation_id).toBe(
    api.submit.mock.calls[1][0].operation_id,
  );
  await waitFor(() =>
    expect(
      (screen.getByLabelText("反馈内容") as HTMLTextAreaElement).value,
    ).toBe(""),
  );
});
