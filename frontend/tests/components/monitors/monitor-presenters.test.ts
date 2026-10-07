import { describe, expect, it } from "vitest";
import { ApiRequestError } from "@/request";
import {
  readMonitorFailure,
  topicStatusLabel,
  presentUpdatedTopic,
} from "@/components/monitors/monitor-presenters";
import {
  alertHistoryStatusLabels,
  alertMetricLabel,
  alertReasonLabel,
} from "@/components/monitors/alert-presenters";

describe("monitor presentation boundaries", () => {
  it.each([
    ["active", "定时已启用"],
    ["paused", "已暂停"],
    ["archived", "已归档"],
  ] as const)("labels %s without inferring task status", (status, label) => {
    expect(topicStatusLabel(status)).toBe(label);
  });
  it.each([401, 403])("treats HTTP %s as a permission failure", (status) => {
    expect(
      readMonitorFailure(
        new ApiRequestError({
          kind: "http",
          status,
          code: "access_denied",
          message: "拒绝访问",
          requestId: "request-a",
        }),
        "重试",
      ),
    ).toEqual({
      message: "拒绝访问",
      code: "access_denied",
      httpStatus: status,
      requestId: "request-a",
      forbidden: true,
    });
  });
  it.each(["network", "timeout"] as const)(
    "keeps %s failures separate from logout",
    (kind) => {
      const failure = readMonitorFailure(
        new ApiRequestError({ kind, message: "网络故障" }),
        "重试",
      );
      expect(failure.forbidden).toBe(false);
      expect(failure.code).toBe(kind);
    },
  );
  it("provides a stable code for unexpected failures and preserves server error codes", () => {
    expect(readMonitorFailure(new Error("internal"), "请重试")).toEqual({
      message: "请重试",
      code: "unexpected_error",
      forbidden: false,
    });
    expect(
      readMonitorFailure(
        new ApiRequestError({
          kind: "http",
          status: 503,
          code: "dependency_unavailable",
          message: "忙碌",
        }),
        "重试",
      ),
    ).toMatchObject({
      code: "dependency_unavailable",
      httpStatus: 503,
      forbidden: false,
    });
  });
  it("uses supported alert metrics and labels inconclusive, withdrawn and cooldown history", () => {
    expect(alertMetricLabel("negative_count")).toBe("有效负面情感计数");
    expect(alertMetricLabel("heat_increment")).toBe("同公式热度增量");
    expect(alertHistoryStatusLabels).toEqual({
      blocked: "条件未满足",
      unknown: "无法判定",
      below_threshold: "未达阈值",
      cooldown: "冷却中",
      triggered: "已触发",
      withdrawn: "输入已撤回",
    });
    expect(alertReasonLabel("insufficient_inputs")).toContain("无法判定");
    expect(alertReasonLabel("alert_delivery_unknown")).toContain(
      "不会自动重发",
    );
    expect(alertReasonLabel("source_withdrawn")).toContain("许可已失效");
    expect(alertReasonLabel(null)).toBe("");
    expect(alertReasonLabel("new_backend_reason")).toContain("条件尚未满足");
  });
});

it("uses local saved updates without masking a newer server topic or mixing IDs", () => {
  const original = {
    id: "topic-a",
    current_version: 2,
    updated_at: "2026-10-01T02:00:00Z",
  } as HotKeyAPI.MonitorTopicView;
  const saved = { ...original, status: "paused" as const };
  expect(presentUpdatedTopic(original, saved)).toBe(saved);
  expect(presentUpdatedTopic(original, { ...saved, id: "other" })).toBe(
    original,
  );
  expect(presentUpdatedTopic(original, { ...saved, current_version: 1 })).toBe(
    original,
  );
  expect(
    presentUpdatedTopic(original, {
      ...saved,
      updated_at: "2026-10-01T01:00:00Z",
    }),
  ).toBe(original);
  const newVersion = { ...saved, current_version: 3 };
  expect(presentUpdatedTopic(original, newVersion)).toBe(newVersion);
});
