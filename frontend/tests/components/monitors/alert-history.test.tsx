// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ history: vi.fn() }));
vi.mock("@/api/gerentufagaojing", () => ({ listAlertHistory: api.history }));
import { AlertHistory } from "@/components/monitors/alert-history";
import { ApiRequestError } from "@/request";
const row: HotKeyAPI.AlertEvaluationView = {
  id: "evaluation-a",
  rule_id: "rule-a",
  rule_version: 3,
  window_start: "2026-10-04T00:00:00Z",
  window_end: "2026-10-04T01:00:00Z",
  status: "triggered",
  reason: null,
  value: 0,
  cooldown_until: "2026-10-04T02:00:00Z",
  created_at: "2026-10-04T01:00:00Z",
};
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);
it("shows loading, the server values, and marks retained history stale when refresh fails", async () => {
  let resolve!: (rows: HotKeyAPI.AlertEvaluationView[]) => void;
  api.history
    .mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    )
    .mockRejectedValueOnce(
      new ApiRequestError({
        kind: "http",
        status: 503,
        code: "history_busy",
        message: "忙碌",
      }),
    )
    .mockResolvedValueOnce([
      { ...row, status: "withdrawn", value: null, reason: "source_withdrawn" },
    ]);
  render(<AlertHistory ruleId="rule-a" />);
  expect(
    screen
      .getByRole("status", { name: "正在读取评估历史" })
      .getAttribute("aria-busy"),
  ).toBe("true");
  resolve([row]);
  await screen.findByText("已触发");
  expect(api.history).toHaveBeenCalledWith({ rule_id: "rule-a", limit: 50 });
  fireEvent.click(screen.getByRole("button", { name: "刷新历史" }));
  await screen.findByText("已过期");
  expect(screen.getByText("已触发")).toBeTruthy();
  expect(screen.getByText("history_busy · 503")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "登录" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重试历史" }));
  await screen.findByText("输入已撤回");
  expect(screen.queryByText("已过期")).toBeNull();
  expect(screen.getByText("未知")).toBeTruthy();
  expect(screen.getByText("输入许可已失效。")).toBeTruthy();
});
it.each([401, 403])("shows permission state for %s", async (status) => {
  api.history.mockRejectedValue(
    new ApiRequestError({
      kind: "http",
      status,
      code: "access_denied",
      message: "拒绝访问",
    }),
  );
  render(<AlertHistory ruleId="rule-a" />);
  await screen.findByRole("status", { name: "无权读取告警历史" });
  expect(screen.getByRole("link", { name: "登录" })).toBeTruthy();
});
it("keeps an empty history distinct from a failed read and retries it", async () => {
  api.history
    .mockRejectedValueOnce(
      new ApiRequestError({ kind: "network", message: "offline" }),
    )
    .mockResolvedValueOnce([]);
  render(<AlertHistory ruleId="rule-a" />);
  await screen.findByText("network");
  expect(screen.queryByText("尚无评估记录")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重试历史" }));
  await screen.findByText("尚无评估记录");
  expect(screen.queryByRole("alert")).toBeNull();
});
it("ignores a response after leaving the history", async () => {
  let resolve!: (rows: HotKeyAPI.AlertEvaluationView[]) => void;
  api.history.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const view = render(<AlertHistory ruleId="rule-a" />);
  view.unmount();
  resolve([row]);
  await waitFor(() => expect(screen.queryByText("已触发")).toBeNull());
});
