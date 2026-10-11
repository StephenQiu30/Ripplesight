import * as UI from "@/components/ui/content";
import { Badge } from "@/components/ui/badge";

// Describe the existing versioned policy; the API remains the eligibility authority.
const supportedFormula = "attention-v1-48h-halflife24h";
const windowMs = 48 * 60 * 60 * 1000;

export function EventQualification({
  data,
}: {
  data: HotKeyAPI.EventAttentionView;
}) {
  const end =
    typeof data.window_end === "string" &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(data.window_end)
      ? Date.parse(data.window_end)
      : NaN;
  const start = new Date(end - windowMs).getTime();
  const counts = [
    data.participant_count,
    data.editorial_participant_count,
    data.signal_participant_count,
  ];
  const validCounts =
    counts.every((value) => Number.isSafeInteger(value) && value >= 0) &&
    data.editorial_participant_count + data.signal_participant_count ===
      data.participant_count;
  const explained =
    data.formula_version === supportedFormula &&
    Number.isFinite(start) &&
    validCounts &&
    data.eligible ===
      (data.participant_count >= 2 && data.editorial_participant_count >= 1);
  const receipt =
    data.eligible === true
      ? "满足"
      : data.eligible === false
        ? "未满足"
        : "未提供";
  return (
    <UI.Content
      as="section"
      aria-label="热榜资格说明"
      className="flex min-w-0 flex-col gap-2 rounded-lg border p-4 wrap-anywhere"
    >
      <UI.Heading level={3}>热榜资格说明</UI.Heading>
      <UI.Content className="flex flex-wrap items-center gap-2">
        <Badge
          variant={explained && data.eligible ? "secondary" : "outline"}
          className="h-auto min-h-5 max-w-full text-left whitespace-normal"
        >
          {explained
            ? data.eligible
              ? "满足当前48小时热榜条件"
              : "尚未满足当前48小时热榜条件"
            : "资格说明待确定"}
        </Badge>
        <UI.Text size="sm">服务端资格回执：{receipt}</UI.Text>
      </UI.Content>
      <UI.Text size="sm" tone="muted" className="break-all">
        规则版本：{data.formula_version || "未提供"}
      </UI.Text>
      {explained ? (
        <>
          <UI.Text size="sm">
            48小时窗口（UTC）：
            <UI.Timestamp dateTime={new Date(start).toISOString()}>
              {new Date(start).toISOString()}
            </UI.Timestamp>
            {" 至 "}
            <UI.Timestamp dateTime={new Date(end).toISOString()}>
              {new Date(end).toISOString()}
            </UI.Timestamp>
            。起点不计入，终点计入；未来材料不计入。
          </UI.Text>
          <UI.Text size="sm">
            去重参与者：实际 {data.participant_count} 个 / 至少 2 个。
          </UI.Text>
          <UI.Text size="sm">
            其中编辑参与者：实际 {data.editorial_participant_count} 个 / 至少 1
            个。
          </UI.Text>
          {!data.eligible ? (
            <UI.Text size="sm">
              未满足原因：
              {[
                data.participant_count < 2 ? "去重参与者不足2个" : null,
                data.editorial_participant_count < 1 ? "缺少编辑参与者" : null,
              ]
                .filter(Boolean)
                .join("；")}
              。
            </UI.Text>
          ) : null}
          <UI.Text size="sm" tone="muted">
            优先按来源组，其次按主体，均未配置时按来源计数。参与者不等于帖子数、作者数或独立事实确认。
          </UI.Text>
        </>
      ) : (
        <UI.Text size="sm" tone="muted">
          {data.formula_version !== supportedFormula
            ? "当前规则版本未提供或暂不支持，暂不推断窗口、最低样本及未满足原因。"
            : "窗口、样本计数或资格回执不完整或不一致，暂不推断未满足原因。"}
        </UI.Text>
      )}
      <UI.Text size="sm" tone="muted">
        48小时来源参与热榜用于阅读排序，不代表事件已多方证实，也不替代24小时相关帖、作者和新事实统计。覆盖缺口与趋势不可比单独展示。
      </UI.Text>
    </UI.Content>
  );
}
