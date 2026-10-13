"use client";

import { useState } from "react";
import Link from "next/link";
import { Content, Heading, Text } from "@/components/ui/content";
import { Button } from "@/components/ui/button";
import { publicationTime } from "@/components/publication/reading-format";

const states = {
  triggered: "达到报道负面突增规则",
  not_triggered: "未达到突增规则",
  insufficient_data: "数据不足，暂不可判定",
  unavailable: "判定依据不可用",
  not_configured: "判定规则未配置，真实阈值待校准",
  empty: "暂无可公开判定的事件",
} satisfies Record<HotKeyAPI.PublicNegativeSurgeView["state"], string>;

const reasons = {
  rule_not_configured: "尚未配置经过校准的规则",
  analysis_unavailable: "报道分析依据不可用",
  time_unknown: "材料发现时间未知或异常",
  evidence_conflict: "报道依据存在冲突",
  current_empty: "当前24小时没有报道样本",
  previous_empty: "前一24小时没有基线样本",
  current_samples_insufficient: "当前窗口有效样本不足",
  previous_samples_insufficient: "前一窗口有效样本不足",
  current_coverage_low: "当前窗口分析覆盖不足",
  previous_coverage_low: "前一窗口分析覆盖不足",
  source_identity_missing: "报道来源身份缺失",
  sources_changed: "两期来源集合发生变化",
  sources_insufficient: "可比较来源数量不足",
  source_samples_insufficient: "至少一个来源的有效样本不足",
  source_coverage_low: "至少一个来源的分析覆盖不足",
  negative_count_below_threshold: "负面报道数量未达阈值",
  count_increase_below_threshold: "负面数量增量未达阈值",
  ratio_increase_below_threshold: "整体负面占比增幅未达阈值",
  source_ratio_increase_below_threshold: "至少一个来源的占比增幅未达阈值",
} satisfies Record<HotKeyAPI.NegativeSurgeReason, string>;

const number = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 });
const percent = (value?: number | string | null) =>
  value == null ? "未知" : `${number.format(Number(value) * 100)}%`;

/** Render server decisions and gaps, never recalculate a rule in the browser. */
export function NegativeSurge({
  surge,
  failure,
}: {
  surge?: HotKeyAPI.PublicNegativeSurgeView | null;
  failure?: { status?: number };
}) {
  const [expanded, setExpanded] = useState(false);
  const denied = [401, 403].includes(failure?.status ?? 0);
  const view = failure ? undefined : surge;
  return (
    <Content
      as="section"
      layout="stack"
      className="min-w-0 gap-3"
      aria-label="报道负面突增提醒"
    >
      <Heading level={3} appearance="reading">
        报道负面突增提醒
      </Heading>
      <Text
        size="sm"
        tone={view?.state === "triggered" ? "destructive" : "muted"}
      >
        {failure
          ? denied
            ? "无权读取负面突增判定"
            : "负面突增判定读取失败，请重新加载事件"
          : view
            ? states[view.state]
            : "暂无后端判定依据，当前状态未知"}
      </Text>
      {view ? (
        <>
          <Text size="xs" tone="muted">
            可判定 {view.evaluated_events}/{view.total_events} 个公开事件 ·
            已判定触发 {view.triggered_count} · 未触发{" "}
            {view.not_triggered_count}
          </Text>
          <Text size="xs" tone="muted">
            数据不足 {view.insufficient_count} · 依据不可用{" "}
            {view.unavailable_count} · 规则未配置 {view.not_configured_count}
            {view.evaluated_events < view.total_events || !view.rule
              ? "；全站突增总数未知。"
              : "。"}
          </Text>
          {view.rule ? (
            <Content layout="stack" className="gap-1">
              <Text size="xs" tone="muted">
                规则 {view.rule.policy_id} · 两窗及每来源有效样本至少{" "}
                {view.rule.min_valid_samples} · 分析覆盖至少{" "}
                {percent(view.rule.min_analysis_coverage)}（比例{" "}
                {view.rule.min_analysis_coverage}）
              </Text>
              <Text size="xs" tone="muted">
                来源集合一致且至少 {view.rule.min_sources} 个；负面数量至少{" "}
                {view.rule.min_negative_count}、增加至少{" "}
                {view.rule.min_negative_count_increase}{" "}
                条；整体和每来源占比均增加至少{" "}
                {number.format(Number(view.rule.min_ratio_increase) * 100)}{" "}
                个百分点（比例差 {view.rule.min_ratio_increase}）。
              </Text>
            </Content>
          ) : (
            <Text size="xs" tone="muted">
              阈值尚未冻结，不使用默认数值判定；样本缺口见各事件。
            </Text>
          )}
          {view.events.slice(0, expanded ? 20 : 5).map((event) => (
            <Content
              key={event.event_id}
              layout="stack"
              className="gap-1 border-t pt-3"
            >
              <Link
                href={event.reading_url}
                className="text-sm break-words underline underline-offset-4"
              >
                {event.title}
              </Link>
              <Text
                size="xs"
                tone={event.state === "triggered" ? "destructive" : "muted"}
              >
                {states[event.state]}
              </Text>
              {(
                [
                  ["当前24小时", event.current],
                  ["前一24小时", event.previous],
                ] as const
              ).map(([label, window]) => (
                <Text key={label} size="xs" tone="muted">
                  {label}：
                  {window
                    ? `有效 ${window.valid_count}/${window.sample_count} · 负面 ${window.negative} · 占有效样本 ${percent(window.negative_ratio)} · 分析覆盖 ${percent(window.analysis_coverage)}`
                    : "分析依据未知"}
                </Text>
              ))}
              {event.ratio_increase != null ? (
                <Text size="xs" tone="muted">
                  占比变化 {number.format(event.ratio_increase * 100)} 个百分点
                  · 负面数量变化 {event.negative_count_increase} 条
                </Text>
              ) : null}
              {event.reasons.length ? (
                <Text size="xs" tone="muted">
                  {event.reasons.map((reason) => reasons[reason]).join("；")}
                </Text>
              ) : null}
            </Content>
          ))}
          {view.events.length ? (
            <Text size="xs" tone="muted">
              已列 {Math.min(view.events.length, expanded ? 20 : 5)}/
              {view.total_events} 个事件，触发优先；进入事件核对公开报道依据。
            </Text>
          ) : null}
          {view.events.length > 5 ? (
            <Button
              variant="ghost"
              size="sm"
              className="self-start"
              onClick={() => setExpanded((value) => !value)}
              aria-expanded={expanded}
            >
              {expanded ? "收起判定事件" : "展开更多判定事件"}
            </Button>
          ) : null}
          <Text size="xs" tone="muted">
            截至 {publicationTime(view.snapshot_at)} ·
            按材料发现时间比较相邻两个24小时窗口（起点不含、终点包含）。
          </Text>
        </>
      ) : null}
      <Text size="xs" tone="muted">
        仅表示当前可公开报道样本的规则结果，不代表评论民意或完整舆情；页面读取不会发送通知。
      </Text>
    </Content>
  );
}
