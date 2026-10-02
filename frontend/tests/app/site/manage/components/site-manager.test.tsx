// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn() }));
vi.mock("@/api/zhandiziliao", () => ({
  getOperatorSiteConfiguration: api.get,
  saveOperatorSiteConfiguration: api.save,
}));

import { SiteManager } from "@/app/site/manage/components/site-manager";
const current = {
  revision: 1,
  contact_enabled: true,
  contact_title: "联系",
  contact_text: "当前资料",
  contact_url: null,
  wechat_qr_url: null,
  feishu_qr_url: null,
  updated_at: null,
};
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
it("keeps the operation identity and user's edit after an uncertain save", async () => {
  api.get.mockResolvedValue(current);
  api.save
    .mockRejectedValueOnce(new Error("lost response"))
    .mockResolvedValueOnce({ ...current, revision: 2 });
  render(<SiteManager />);
  expect(api.get).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("运营令牌"), {
    target: { value: "controlled-operator" },
  });
  fireEvent.click(screen.getByRole("button", { name: "读取配置" }));
  await screen.findByText("当前修订 1");
  fireEvent.change(screen.getByLabelText("联系说明"), {
    target: { value: "准备保存的真实资料" },
  });
  fireEvent.change(screen.getByLabelText("修改原因"), {
    target: { value: "维护联系资料" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
  await screen.findByRole("alert");
  expect((screen.getByLabelText("联系说明") as HTMLTextAreaElement).value).toBe(
    "准备保存的真实资料",
  );
  fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
  await screen.findByText("当前修订 2");
  expect(api.save.mock.calls[0][0]).toEqual(api.save.mock.calls[1][0]);
  expect(api.save.mock.calls[0][0]).toMatchObject({
    expected_revision: 1,
    wechat_qr_action: "keep",
    feishu_qr_action: "keep",
  });
});
it("ignores a late response after the operator token changes", async () => {
  let finish: (value: typeof current) => void = () => {};
  api.get.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<SiteManager />);
  fireEvent.change(screen.getByLabelText("运营令牌"), {
    target: { value: "first-token" },
  });
  fireEvent.click(screen.getByRole("button", { name: "读取配置" }));
  fireEvent.change(screen.getByLabelText("运营令牌"), {
    target: { value: "second-token" },
  });
  finish(current);
  await waitFor(() => expect(screen.queryByLabelText("联系说明")).toBeNull());
  expect(api.save).not.toHaveBeenCalled();
});
