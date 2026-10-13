"use client";

import { Content, InlineCode, Text } from "@/components/ui/content";
import { HistoryCurve } from "@/components/ui/history-curve";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { publicationTime } from "./reading-format";

const reasons: Record<
  NonNullable<HotKeyAPI.PublicHeatPoint["reason"]>,
  string
> = {
  missing: "缺少小时记录",
  incomplete: "采集不完整或独立来源不足",
  recomputed: "历史补算，未作为历史记录连线",
  provenance_unknown: "旧记录缺少计算依据",
  invalid: "时间或计算依据异常",
  not_public: "历史输入未全部公开或已失效",
  capacity: "历史候选超过读取容量",
  source_changed: "来源口径变化，不可直接比较",
  zero_baseline: "基线为零，无法计算增速",
};
export function heatReason(reason: HotKeyAPI.PublicHeatPoint["reason"]) {
  return reason ? reasons[reason] : "数据不足";
}
export function heatTrendLabel(trend?: HotKeyAPI.PublicHeatTrend) {
  if (!trend || trend.state !== "available" || trend.percent == null)
    return `${trend?.state === "unavailable" ? "依据不可用" : "数据不足"} · ${heatReason(trend?.reason)}`;
  return `${trend.direction === "up" ? "上升" : trend.direction === "down" ? "下降" : "持平"} ${Math.abs(trend.percent).toFixed(1)}% · 与6小时前比较`;
}

/** A shared read-only curve and keyboard-accessible audit table. */
export function HeatHistory({
  history,
}: {
  history?: HotKeyAPI.PublicHeatHistory | null;
}) {
  if (!history)
    return (
      <Text size="xs" tone="muted">
        历史依据未返回
      </Text>
    );
  const valid = history.points.filter((point) => point.value != null).length;
  return (
    <Content layout="stack" className="min-w-0 gap-1" aria-label="事件热度历史">
      <Text size="xs" tone="muted">
        {heatTrendLabel(history.trend)}
      </Text>
      {valid ? (
        <HistoryCurve
          points={history.points.map((point) => ({
            at: point.window_end,
            value: point.value,
            segment: point.segment_key,
          }))}
          label={`最近48小时热度计算记录，${valid}个有效点，缺口不连线`}
        />
      ) : null}
      <Text size="xs" tone="muted">
        本站公开报道 · 48小时滚动热度 · {valid}/48个有效小时记录
        {history.state !== "available"
          ? ` · ${heatReason(history.reason)}`
          : ""}
      </Text>
      <Collapsible>
        <CollapsibleTrigger asChild>
          <Button size="sm" variant="ghost">
            查看历史依据
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <Content layout="stack" className="gap-2 py-2">
            <Text size="xs" tone="muted">
              按小时延迟计算；计算时间不代表窗口截止时已知。仅当前事件修订{" "}
              {history.event_revision}
              ，修订后历史可能不足。来源口径变化或缺口不连线。
            </Text>
            <Text size="xs" tone="muted">
              公式 <InlineCode>{history.formula_version}</InlineCode> ·
              48小时窗口、24小时半衰期、独立来源加权；不是平台原生排名或互动总量。
            </Text>
            <Table aria-label="小时热度计算依据">
              <TableHeader>
                <TableRow>
                  <TableHead>窗口截止</TableHead>
                  <TableHead>计算时间</TableHead>
                  <TableHead>热度 / 来源数</TableHead>
                  <TableHead>依据状态</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.points.map((point, index) => (
                  <TableRow key={point.window_end}>
                    <TableCell className="whitespace-nowrap">
                      {publicationTime(point.window_end)}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      {point.computed_at
                        ? publicationTime(point.computed_at)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {point.value != null
                        ? `${point.value.toFixed(2)} / ${point.participant_count ?? "—"}`
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {point.reason
                        ? heatReason(point.reason)
                        : index > 0 &&
                            history.points[index - 1].segment_key &&
                            point.segment_key !==
                              history.points[index - 1].segment_key
                          ? "来源口径变化，断开连线"
                          : "合格计算记录"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Content>
        </CollapsibleContent>
      </Collapsible>
    </Content>
  );
}
