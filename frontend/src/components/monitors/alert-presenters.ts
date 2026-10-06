export function alertReasonLabel(reason: string | null) {
  if (!reason) return "";
  const labels: Record<string, string> = {
    notification_disabled: "通知发送尚未启用。",
    alert_target_unavailable: "通知目标当前不可用。",
    alert_target_stale: "通知目标的版本、订阅或验证条件尚未满足。",
    alert_target_unverified: "当前通知目标尚无已确认的送达回执。",
    alert_topic_stale: "关注规则已变更，请重新保存告警。",
    alert_delivery_unknown: "上次送达结果未知，需人工核查；不会自动重发。",
    alert_cooldown: "规则处于冷却期。",
    alert_delivery_not_admitted: "投递准入条件尚未满足。",
    alert_input_deleted: "固定输入已删除，该结果已撤回。",
    notifications_disabled: "通知发送尚未启用。",
    target_unavailable: "通知目标未就绪。",
    target_not_verified: "通知目标尚未验证。",
    target_revision_changed: "通知目标已变更，请重新选择。",
    topic_version_changed: "关注规则已变更，请重新保存告警。",
    insufficient_inputs: "缺少可用的固定输入，无法判定。",
    source_withdrawn: "输入许可已失效。",
  };
  return labels[reason] ?? "条件尚未满足，请核对关注规则、有效输入与通知目标。";
}

export const alertHistoryStatusLabels: Record<
  HotKeyAPI.AlertEvaluationView["status"],
  string
> = {
  blocked: "条件未满足",
  unknown: "无法判定",
  below_threshold: "未达阈值",
  cooldown: "冷却中",
  triggered: "已触发",
  withdrawn: "输入已撤回",
};

export function alertMetricLabel(metric: HotKeyAPI.AlertRuleInput["metric"]) {
  return metric === "negative_count" ? "有效负面情感计数" : "同公式热度增量";
}
