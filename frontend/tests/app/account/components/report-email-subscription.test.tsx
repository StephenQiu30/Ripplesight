// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  get: vi.fn(),
  save: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock("@/api/gerenbaogaotongzhi", () => ({
  getReportEmailSubscription: api.get,
  updateReportEmailSubscription: api.save,
}));
vi.mock("sonner", () => ({
  toast: { success: api.success, error: api.error },
}));
import { ReportEmailSubscription } from "@/app/account/components/report-email-subscription";

const subscription: HotKeyAPI.ReportEmailSubscriptionView = {
  email: "reader@example.com",
  enabled: false,
  revision: 2,
  target_name: "我的报告邮箱",
  delivery_available: false,
  email_matches_target: true,
};
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("saves a personal opt-in without a recipient override or operator credential", async () => {
  api.get.mockResolvedValue(subscription);
  api.save.mockResolvedValue({ ...subscription, enabled: true, revision: 3 });
  render(<ReportEmailSubscription />);
  await screen.findByText("收件邮箱：reader@example.com");
  expect(screen.getByText(/平台邮件发送服务尚未就绪/)).toBeDefined();
  fireEvent.click(screen.getByRole("switch", { name: "订阅报告邮件" }));
  await waitFor(() =>
    expect(api.save).toHaveBeenCalledWith(
      {
        operation_id: expect.any(String),
        expected_revision: 2,
        enabled: true,
      },
      { signal: expect.any(AbortSignal) },
    ),
  );
  await waitFor(() =>
    expect(
      screen
        .getByRole("switch", { name: "订阅报告邮件" })
        .getAttribute("aria-checked"),
    ).toBe("true"),
  );
  expect(api.success).toHaveBeenCalled();
});

it("requires an account email binding and offers recovery for failed reads", async () => {
  api.get
    .mockRejectedValueOnce(new Error("unavailable"))
    .mockResolvedValueOnce({
      ...subscription,
      email: null,
      revision: 0,
      email_matches_target: false,
    });
  render(<ReportEmailSubscription />);
  fireEvent.click(await screen.findByRole("button", { name: "重试" }));
  await screen.findByText("收件邮箱：尚未绑定");
  expect(
    screen
      .getByRole("switch", { name: "订阅报告邮件" })
      .hasAttribute("disabled"),
  ).toBe(true);
  expect(api.save).not.toHaveBeenCalled();
});
