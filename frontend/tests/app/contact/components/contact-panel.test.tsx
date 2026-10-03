// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const notifications = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: notifications }));
const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/api/zhandiziliao", () => ({ getPublicContact: api.get }));
import { ContactPanel } from "@/app/contact/components/contact-panel";
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
it("uses a toast for request failure and retains the recovery control", async () => {
  api.get.mockRejectedValue(new Error("offline"));
  render(<ContactPanel />);
  await waitFor(() =>
    expect(notifications.error).toHaveBeenCalledWith(
      "联系资料读取失败，请重新读取。",
    ),
  );
  expect(screen.queryByText("联系资料读取失败，请重新读取。")).toBeNull();
  expect(screen.getByRole("button", { name: "重新读取" })).toBeTruthy();
});
it("removes both QR images and contact text after current configuration is disabled", async () => {
  api.get
    .mockResolvedValueOnce({
      enabled: true,
      title: "联系维护者",
      text: "当前联系资料",
      url: null,
      wechat_qr_url: "/api/site/contact/qr/first.png",
      feishu_qr_url: "/api/site/contact/qr/second.png",
      revision: 1,
    })
    .mockResolvedValueOnce({
      enabled: false,
      title: null,
      text: null,
      url: null,
      wechat_qr_url: null,
      feishu_qr_url: null,
      revision: 2,
    });
  render(<ContactPanel />);
  await screen.findByAltText("微信二维码");
  expect(screen.getByAltText("飞书二维码")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  await screen.findByText(
    "维护者尚未启用公开联系资料。登录后可以提交站内反馈。",
  );
  expect(screen.queryByText("当前联系资料")).toBeNull();
  expect(screen.queryByAltText("微信二维码")).toBeNull();
  expect(screen.queryByAltText("飞书二维码")).toBeNull();
});
