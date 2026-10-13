import Link from "next/link";
import { Content, Heading, Text } from "@/components/ui/content";
import { publicationTime } from "@/components/publication/reading-format";

const states: Record<string, string> = {
  positive: "正面",
  neutral: "中性",
  negative: "负面",
  not_analyzed: "未分析",
  pending: "分析待完成",
  failed: "分析失败",
  invalid: "结果无效",
  not_relevant: "不相关",
  unavailable: "依据不可用",
  conflict: "依据冲突",
  backfill: "补录",
};
const percent = (value: number | null) =>
  value == null
    ? "未知"
    : new Intl.NumberFormat("zh-CN", {
        style: "percent",
        maximumFractionDigits: 1,
      }).format(value);

/** Descriptive public report samples; never imply comment opinion or a surge. */
export function ReportSentiment({
  sentiment,
  compact = false,
  reports = [],
}: {
  sentiment?: HotKeyAPI.PublicReportSentimentView | null;
  compact?: boolean;
  reports?: HotKeyAPI.PublicItemView[];
}) {
  if (compact)
    return (
      <Text size="xs" tone="muted">
        报道情感{" "}
        {sentiment
          ? `有效 ${sentiment.current.valid_count}/${sentiment.current.sample_count} · 负面占有效样本 ${percent(sentiment.current.negative_ratio)}`
          : "暂无公开分析依据"}
      </Text>
    );
  const evidence =
    sentiment?.samples
      .map((sample) => ({
        sample,
        report: reports.find((report) => report.id === sample.content_id),
      }))
      .filter((entry) => entry.report) ?? [];
  return (
    <Content
      as="section"
      layout="stack"
      className="min-w-0 gap-3"
      aria-label="公开报道情感"
    >
      <Heading level={3} appearance="reading">
        公开报道情感
      </Heading>
      {sentiment ? (
        <>
          {(
            [
              ["过去24小时", sentiment.current],
              ["前一24小时", sentiment.previous],
            ] as const
          ).map(([label, window]) => (
            <Content key={label} layout="stack" className="gap-1">
              <Text size="sm">
                {label} · 有效 {window.valid_count}/{window.sample_count}
              </Text>
              <Text size="xs" tone="muted">
                正面 {window.positive} · 中性 {window.neutral} · 负面{" "}
                {window.negative}
              </Text>
              <Text size="xs" tone="muted">
                负面占有效样本 {percent(window.negative_ratio)} · 分析覆盖{" "}
                {percent(window.analysis_coverage)}
              </Text>
              <Text size="xs" tone="muted">
                {publicationTime(window.start)} 至 {publicationTime(window.end)}
                （起点不含）
              </Text>
              {Object.entries(window.excluded_counts).length ? (
                <Text size="xs" tone="muted">
                  排除：
                  {Object.entries(window.excluded_counts)
                    .map(
                      ([state, count]) =>
                        `${states[state] ?? "依据未知"} ${count}`,
                    )
                    .join(" · ")}
                </Text>
              ) : null}
              <Text size="xs" tone="muted">
                {window.source_keys.length} 个报道来源
              </Text>
            </Content>
          ))}
          {sentiment.time_unknown_count ? (
            <Text size="xs" tone="muted">
              另有 {sentiment.time_unknown_count}{" "}
              条材料发现时间未知，未进入窗口。
            </Text>
          ) : null}
          {evidence.length ? (
            <Content layout="stack" className="gap-2">
              <Text size="xs" tone="muted">
                已列报道依据 {Math.min(evidence.length, 5)}/{evidence.length}
                ；全部报道见来源列表。
              </Text>
              {evidence.slice(0, 5).map(({ sample, report }) => (
                <Link
                  key={sample.content_id}
                  href={report!.reading_url}
                  className="text-sm break-words underline underline-offset-4"
                >
                  {report!.title} ·{" "}
                  {sample.backfill
                    ? "补录，未计有效样本"
                    : sample.label && sample.state === "valid"
                      ? states[sample.label]
                      : states[sample.state]}
                </Link>
              ))}
            </Content>
          ) : null}
        </>
      ) : (
        <Text size="sm" tone="muted">
          暂无可用的公开报道分析依据。
        </Text>
      )}
      <Text size="xs" tone="muted">
        按材料发现时间分窗；仅代表公开事件报道，不代表评论民意。样本统计本身不判定突增；首页另列后端规则结果与数据缺口。
      </Text>
    </Content>
  );
}
