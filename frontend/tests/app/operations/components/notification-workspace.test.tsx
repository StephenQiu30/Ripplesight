// @vitest-environment happy-dom
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
const notifications = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications }));

const api = vi.hoisted(() => ({
  targets: vi.fn(),
  deliveries: vi.fn(),
  save: vi.fn(),
  resolve: vi.fn(),
}));
vi.mock("@/api/yunyingweihu", () => ({
  listOperatorNotificationTargets: api.targets,
  listOperatorNotificationDeliveries: api.deliveries,
  saveOperatorNotificationTarget: api.save,
  resolveOperatorNotificationDelivery: api.resolve,
}));
import { NotificationWorkspace } from "@/app/operations/components/notification-workspace";
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
it("keeps new targets disabled and the operation identity stable after an uncertain response", async () => {
  api.targets.mockResolvedValue([]);
  api.deliveries.mockResolvedValue({ items: [], next_cursor: null });
  api.save
    .mockRejectedValueOnce(new Error("controlled lost response"))
    .mockResolvedValueOnce({ id: "target" });
  render(<NotificationWorkspace token="operator-test" />);
  await screen.findByText("暂无投递记录。");
  fireEvent.change(screen.getByLabelText("目标名称"), {
    target: { value: "weekly-email" },
  });
  fireEvent.change(
    screen.getByLabelText("收件人邮箱（逗号分隔，最多 20 个）"),
    { target: { value: "reader@example.test" } },
  );
  fireEvent.change(screen.getByLabelText("通知配置原因"), {
    target: { value: "配置主题报告邮件" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存通知目标" }));
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith(
      "通知操作失败，请保留输入后重试。",
    ),
  );
  expect(screen.queryByText("通知操作失败，请保留输入后重试。")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "保存通知目标" }));
  await waitFor(() => expect(api.save).toHaveBeenCalledTimes(2));
  const first = api.save.mock.calls[0][0];
  expect(first).toMatchObject({
    expected_revision: 0,
    target_id: null,
    target: {
      enabled: false,
      recipients: ["reader@example.test"],
      subscriptions: ["report"],
    },
  });
  expect(api.save.mock.calls[1][0].operation_id).toBe(first.operation_id);
  expect(api.save.mock.calls[0][1].headers["X-HotKey-Operator-Token"]).toBe(
    "operator-test",
  );
});
it("submits explicit destination evidence with the frozen unknown delivery revision", async () => {
  api.targets.mockResolvedValue([]);
  api.deliveries.mockResolvedValue({
    items: [
      {
        id: "delivery",
        revision: 7,
        target_id: "target",
        subject_kind: "selected",
        subject_id: "content",
        subject_revision: 3,
        target_revision: 2,
        status: "unknown",
        attempt_count: 1,
        last_error_code: "unknown",
        updated_at: "2026-10-02T02:00:00Z",
        provider_receipt: {},
      },
    ],
    next_cursor: null,
  });
  api.resolve.mockResolvedValue({});
  render(<NotificationWorkspace token="operator-test" />);
  fireEvent.change(await screen.findByLabelText("核对依据"), {
    target: { value: "目的地消息检索确认未送达" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存人工核对" }));
  await waitFor(() =>
    expect(api.resolve).toHaveBeenCalledWith(
      { delivery_id: "delivery" },
      expect.objectContaining({
        expected_revision: 7,
        outcome: "not_delivered",
        reason: "目的地消息检索确认未送达",
      }),
      expect.anything(),
    ),
  );
});
