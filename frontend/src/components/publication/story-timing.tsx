import { Content, InlineCode, Text } from "@/components/ui/content";
import { publicationTime } from "@/components/publication/reading-format";

const activityLabels = {
  new: "24小时内新识别",
  existing_updated: "旧事件进展归入",
  existing: "既有事件",
  unknown: "事件时间待核对",
} as const;

/** These are server-classified system times, independent of material discovery. */
export function StoryTiming({
  timing,
  showEvidence = false,
}: {
  timing: HotKeyAPI.PublicStoryTiming;
  showEvidence?: boolean;
}) {
  return (
    <Content layout="stack" className="min-w-0 gap-1" aria-label="事件时间依据">
      <Text size="xs" tone="muted">
        {activityLabels[timing.activity]} · 系统识别{" "}
        {publicationTime(timing.identified_at)}
        {timing.latest_development_at
          ? ` · 进展归入 ${publicationTime(timing.latest_development_at)}`
          : ""}
      </Text>
      <Text size="xs" tone="muted">
        事件参考 {publicationTime(timing.reference_at)}（
        {timing.reference_basis === "published"
          ? "来源发布时间"
          : timing.reference_basis === "discovered"
            ? "材料发现时间"
            : "依据未知"}
        ） · 发生时间未记录
      </Text>
      <Text size="xs" tone="muted">
        识别指系统建档；进展可能重新归入，不代表首次发生或首次确认。
      </Text>
      {showEvidence && timing.development_fact_ids.length ? (
        <Text size="xs" tone="muted" className="break-all">
          进展事实依据：
          <InlineCode>{timing.development_fact_ids.join(" · ")}</InlineCode>
        </Text>
      ) : null}
    </Content>
  );
}
