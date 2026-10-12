import * as UI from "@/components/ui/content";
import { Badge } from "@/components/ui/badge";

type EvidenceReceipt = Partial<
  Pick<
    HotKeyAPI.EventReadView,
    | "revision"
    | "member_count"
    | "readable_member_count"
    | "evidence_state"
    | "source_counts"
  >
>;

function positiveCount(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

/** Explains current membership size without inferring independent confirmation. */
export function EventEvidence({ event }: { event: EvidenceReceipt }) {
  const total = event.member_count;
  const readable = event.readable_member_count;
  const countsKnown =
    positiveCount(total) && positiveCount(readable) && readable === total;
  const receiptKnown =
    countsKnown &&
    positiveCount(event.revision) &&
    ((event.evidence_state === "complete" && readable === total) ||
      event.evidence_state === "partial");
  const title = !receiptKnown
    ? "证据范围待确定"
    : event.evidence_state === "partial"
      ? "部分证据不可读"
      : total === 1
        ? "单材料线索"
        : "多材料关联";
  const sources = Object.entries(event.source_counts ?? {});
  const sourcesKnown =
    countsKnown &&
    sources.length > 0 &&
    sources.every(([key, count]) => key.trim() && positiveCount(count)) &&
    sources.reduce((sum, [, count]) => sum + count, 0) === readable;

  return (
    <UI.Content
      as="section"
      aria-labelledby="event-evidence-heading"
      className="flex min-w-0 flex-col gap-3 rounded-lg border p-4"
    >
      <UI.Heading id="event-evidence-heading" level={2}>
        当前事件的证据范围
      </UI.Heading>
      <UI.Content className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{title}</Badge>
        <UI.Text size="sm" tone="muted">
          当前事件修订 {positiveCount(event.revision) ? event.revision : "未知"}
        </UI.Text>
      </UI.Content>
      <UI.Text size="sm">
        当前可读成员 {countsKnown ? readable : "未知"}{" "}
        条；不包含无权读取的材料。
      </UI.Text>
      <UI.Text size="sm" tone="muted">
        {!receiptKnown
          ? "计数或证据状态缺失、无效或不一致，暂不能确定线索范围。"
          : event.evidence_state === "partial"
            ? "部分成员已不可读，不能仅凭剩余可读材料确定完整证据范围。"
            : total === 1
              ? "此修订只有一条材料，保留为线索；请结合原文核对主体、动作与时间。"
              : "此修订关联了多条材料，仍需结合原文核对是否为同一事件及是否相互独立。"}
      </UI.Text>
      <UI.Text size="sm" tone="muted" className="wrap-anywhere">
        可读成员来源分布：
        {sourcesKnown
          ? sources
              .map(([source, count]) => `${source} ${count} 条`)
              .join(" · ")
          : "待确定"}
        。成员数及来源数均不代表独立证实或新增事实数；此处不随下方历史成员读取改变。
      </UI.Text>
    </UI.Content>
  );
}
