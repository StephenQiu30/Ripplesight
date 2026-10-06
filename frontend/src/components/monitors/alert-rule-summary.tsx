import * as UI from "@/components/ui/content";
import { alertMetricLabel } from "./alert-presenters";

export function AlertRuleSummary({ rule }: { rule: HotKeyAPI.AlertRuleView }) {
  return (
    <UI.Text tone="muted" size="sm">
      {alertMetricLabel(rule.metric)} ≥{" "}
      <UI.InlineCode>{rule.threshold}</UI.InlineCode>
      {" · "}冷却 <UI.InlineCode>{rule.cooldown_seconds / 60}</UI.InlineCode>{" "}
      分钟
      {" · "}主题规则 <UI.InlineCode>v{rule.topic_rule_version}</UI.InlineCode>
    </UI.Text>
  );
}
