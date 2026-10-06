"use client";

import * as UI from "@/components/ui/content";
import {
  CartesianGrid,
  ChartContainer,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "@/components/ui/chart";
import { EventEmpty } from "./event-reading";
import { eventTime, heatHistoryPoints } from "./reading-model";

export function HeatHistory({
  history,
}: {
  history: HotKeyAPI.EventAttentionView[];
}) {
  const points = heatHistoryPoints(history);
  const known = points.filter((point) => point.heat !== null);
  if (!known.length)
    return (
      <EventEmpty>尚无当前修订的实际小时快照，不绘制热度历史。</EventEmpty>
    );
  if (known.length === 1)
    return (
      <UI.Text size="sm" tone="muted">
        仅有一个实际小时快照：
        <UI.InlineCode>
          {eventTime(new Date(known[0].time).toISOString())}
        </UI.InlineCode>
        ，热度 <UI.InlineCode>{known[0].heat?.toFixed(1)}</UI.InlineCode>
        ；样本不足，不绘制折线。
      </UI.Text>
    );
  const first = known[0];
  const last = known[known.length - 1];
  const peak = Math.max(...known.map((point) => point.heat ?? 0));
  return (
    <UI.Content className="flex min-w-0 flex-col gap-3">
      <UI.Text size="sm" tone="muted">
        热度历史：
        <UI.InlineCode>
          {eventTime(new Date(first.time).toISOString())}
        </UI.InlineCode>{" "}
        至{" "}
        <UI.InlineCode>
          {eventTime(new Date(last.time).toISOString())}
        </UI.InlineCode>
        ，共 <UI.InlineCode>{known.length}</UI.InlineCode> 个实际快照，热度从{" "}
        <UI.InlineCode>{first.heat?.toFixed(1)}</UI.InlineCode> 到{" "}
        <UI.InlineCode>{last.heat?.toFixed(1)}</UI.InlineCode>，最高{" "}
        <UI.InlineCode>{peak.toFixed(1)}</UI.InlineCode>。
        {points.length > known.length ? " 无可参与来源的小时保留为空缺。" : ""}
      </UI.Text>
      <UI.Content aria-hidden="true" className="min-w-0">
        <ChartContainer
          config={{ heat: { label: "热度" } }}
          className="h-48 w-full"
        >
          <LineChart data={points} accessibilityLayer={false}>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="time"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(time: number) =>
                new Date(time).toLocaleTimeString("zh-CN", {
                  timeZone: "Asia/Shanghai",
                  hour: "2-digit",
                  minute: "2-digit",
                })
              }
              tickLine={false}
              axisLine={false}
              minTickGap={40}
            />
            <YAxis tickLine={false} axisLine={false} />
            <Line
              dataKey="heat"
              type="linear"
              stroke="var(--foreground)"
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ChartContainer>
      </UI.Content>
    </UI.Content>
  );
}
