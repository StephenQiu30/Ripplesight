// @vitest-environment happy-dom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ list: vi.fn(), history: vi.fn() }));
vi.mock("@/api/gerentufagaojing", () => ({
  listAlerts: api.list,
  listAlertHistory: api.history,
}));
import { TopicAlerts } from "@/components/monitors/topic-alerts";
import { ApiRequestError } from "@/request";
const rule: HotKeyAPI.AlertRuleView = {
  id: "rule-a",
  name: "主题规则",
  revision: 1,
  enabled: false,
  topic_id: "topic-a",
  topic_rule_version: 2,
  event_id: null,
  metric: "heat_increment",
  threshold: 12.5,
  cooldown_seconds: 600,
  target_id: "target-a",
  target_revision: 1,
  readiness: "blocked",
  reason: "topic_version_changed",
  last_trigger_at: null,
  created_at: "2026-10-04T00:00:00Z",
  updated_at: "2026-10-04T00:00:00Z",
};
beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);
it("only renders this topic's rules, reads history on demand, and has no unread controls", async () => {
  api.list.mockResolvedValue([
    rule,
    { ...rule, id: "other", name: "其他主题规则", topic_id: "other-topic" },
  ]);
  api.history.mockResolvedValue([]);
  render(<TopicAlerts topicId="topic-a" />);
  await screen.findByText("主题规则");
  expect(screen.queryByText("其他主题规则")).toBeNull();
  expect(screen.getByText(/同公式热度增量/)).toBeTruthy();
  expect(screen.getByText("12.5")).toBeTruthy();
  expect(screen.getByText("10")).toBeTruthy();
  expect(screen.queryByText(/未读|已读/)).toBeNull();
  expect(api.history).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "评估历史" }));
  await screen.findByText("尚无评估记录");
  expect(api.history).toHaveBeenCalledWith({ rule_id: "rule-a", limit: 50 });
});
it("does not turn a network error into an empty rule list or logout", async () => {
  api.list
    .mockRejectedValueOnce(
      new ApiRequestError({ kind: "network", message: "offline" }),
    )
    .mockResolvedValueOnce([]);
  render(<TopicAlerts topicId="topic-a" />);
  await screen.findByText("network");
  expect(screen.queryByText("这个主题尚无告警规则")).toBeNull();
  expect(screen.queryByRole("link", { name: "登录" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重试告警" }));
  await screen.findByText("这个主题尚无告警规则");
  expect(
    screen.getByRole("link", { name: "配置告警" }).getAttribute("href"),
  ).toBe("/alerts");
});
it("aborts its request and ignores late results", async () => {
  let resolve!: (rows: HotKeyAPI.AlertRuleView[]) => void;
  api.list.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const view = render(<TopicAlerts topicId="topic-a" />);
  view.unmount();
  expect(api.list.mock.calls[0][0].signal.aborted).toBe(true);
  resolve([rule]);
  await waitFor(() => expect(screen.queryByText("主题规则")).toBeNull());
});
