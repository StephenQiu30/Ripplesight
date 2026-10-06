"use client";

import { useEffect, useState } from "react";
import { getEventHeat, listEventHeatHistory } from "@/api/shijian";
import * as UI from "@/components/ui/content";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import {
  TableHead,
  TableRow,
  TableHeader,
  TableCell,
  TableBody,
  Table,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
} from "@/components/ui/item";
import {
  EventEmpty,
  EventSectionFailure,
} from "@/components/events/event-reading";
import { HeatHistory } from "@/components/events/heat-history";
import { eventTime } from "@/components/events/reading-model";
import { ApiRequestError } from "@/request";

const trends = {
  new: "新出现",
  up: "上升",
  down: "下降",
  flat: "持平",
  unknown: "趋势待确定",
};
const badges = { new: "首次出现", surge: "来源骤增", rising: "持续升温" };
type Result<T> =
  | { status: "ready"; data: T }
  | { status: "error"; error: unknown }
  | { status: "loading" };

export function EventHeat({
  eventId,
  eventRevision,
  onHeatLoaded,
}: {
  eventId: string;
  eventRevision?: number;
  onHeatLoaded?: (heat: HotKeyAPI.EventAttentionView | null) => void;
}) {
  const [current, setCurrent] = useState<Result<HotKeyAPI.EventAttentionView>>({
    status: "loading",
  });
  const [history, setHistory] = useState<
    Result<HotKeyAPI.EventAttentionView[]>
  >({ status: "loading" });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const failed = (error: unknown) =>
      !controller.signal.aborted &&
      !(error instanceof ApiRequestError && error.kind === "cancelled");
    const revisionConflict = () =>
      new ApiRequestError({
        kind: "http",
        code: "event_revision_conflict",
        status: 409,
        message: "事件修订已变化，请刷新事件详情。",
      });
    void getEventHeat({ event_id: eventId }, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        if (
          eventRevision != null &&
          data.event_revision != null &&
          data.event_revision !== eventRevision
        )
          throw revisionConflict();
        setCurrent({ status: "ready", data });
        onHeatLoaded?.(data);
      })
      .catch((error: unknown) => {
        if (failed(error)) {
          setCurrent({ status: "error", error });
          onHeatLoaded?.(null);
        }
      });
    void listEventHeatHistory(
      { event_id: eventId, limit: 48 },
      { signal: controller.signal },
    )
      .then((page) => {
        if (controller.signal.aborted) return;
        if (
          eventRevision != null &&
          page.event_revision != null &&
          page.event_revision !== eventRevision
        )
          throw revisionConflict();
        setHistory({
          status: "ready",
          data: page.items.filter(
            (row) =>
              row.event_revision == null ||
              page.event_revision == null ||
              row.event_revision === page.event_revision,
          ),
        });
      })
      .catch((error: unknown) => {
        if (failed(error)) setHistory({ status: "error", error });
      });
    return () => controller.abort();
  }, [eventId, eventRevision, retry, onHeatLoaded]);
  function refresh() {
    setCurrent({ status: "loading" });
    setHistory({ status: "loading" });
    onHeatLoaded?.(null);
    setRetry((value) => value + 1);
  }
  const data = current.status === "ready" ? current.data : null;
  return (
    <UI.Content
      as="section"
      className="flex min-w-0 flex-col gap-4"
      aria-labelledby="event-heat-heading"
    >
      <UI.Heading id="event-heat-heading">当前事件热度</UI.Heading>
      <UI.Text size="sm" tone="muted">
        热度和小时历史对应事件当前修订。
      </UI.Text>
      {current.status === "error" ? (
        <EventSectionFailure
          title="热度读取失败"
          error={current.error}
          retry={refresh}
        />
      ) : !data ? (
        <Skeleton
          aria-label="正在读取热度"
          className="h-12 w-full motion-reduce:animate-none"
        />
      ) : (
        <>
          <UI.Content className="flex flex-wrap items-center gap-3">
            <UI.Text size="sm">
              48 小时热度{" "}
              <UI.InlineCode>
                {data.participant_count ? data.heat.toFixed(1) : "待确定"}
              </UI.InlineCode>
            </UI.Text>
            <UI.Text size="sm">
              <UI.InlineCode>{data.participant_count}</UI.InlineCode>{" "}
              个独立参与者
            </UI.Text>
            <UI.Text size="sm">
              {trends[data.trend]}
              {data.trend_pct != null ? (
                <UI.InlineCode>
                  {" "}
                  {data.trend_pct > 0 ? "+" : ""}
                  {data.trend_pct.toFixed(1)}%
                </UI.InlineCode>
              ) : null}
            </UI.Text>
            {data.badges.map((value) => (
              <Badge key={value} variant="secondary">
                {badges[value]}
              </Badge>
            ))}
          </UI.Content>
          <UI.Text size="sm" tone="muted">
            编辑来源 {data.editorial_participant_count} 个，讨论来源{" "}
            {data.signal_participant_count} 个。
            {data.eligible
              ? "满足热榜条件。"
              : "至少两个独立参与者且含一个编辑来源后进入热榜。"}
            {data.complete ? "" : " 部分来源尚未完成及时采集。"}
            {data.uncomparable_participant_count
              ? ` ${data.uncomparable_participant_count} 个参与者因新增或采集时钟不足未用于趋势比较。`
              : ""}
          </UI.Text>
          {data.interaction ? (
            <UI.Content className="flex flex-col gap-2">
              <UI.Text size="sm">
                互动热度{" "}
                <UI.InlineCode>
                  {data.interaction.score == null
                    ? "待确定"
                    : data.interaction.score.toFixed(2)}
                </UI.InlineCode>
              </UI.Text>
              <UI.Text size="sm" tone="muted">
                按赞、评、转、浏览计算独立指标，未知值保留。
                {data.interaction.rising_state === "insufficient"
                  ? "真实历史样本不足，暂不判断升温。"
                  : data.interaction.rising_state === "rising"
                    ? "近期互动增量达到基线三倍。"
                    : "近期互动保持平稳。"}
              </UI.Text>
            </UI.Content>
          ) : null}
        </>
      )}
      {history.status === "error" ? (
        <EventSectionFailure
          title="热度历史读取失败"
          error={history.error}
          retry={refresh}
        />
      ) : history.status === "loading" ? (
        <Skeleton
          aria-label="正在读取热度历史"
          className="h-48 w-full motion-reduce:animate-none"
        />
      ) : (
        <HeatHistory history={history.data} />
      )}
      {data ? (
        <Collapsible>
          <CollapsibleTrigger asChild>
            <Button variant="ghost">热度计算与来源明细</Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="pt-4">
            <UI.Content className="flex flex-col gap-4">
              <UI.Text size="sm" tone="muted">
                <UI.InlineCode>{data.formula_version}</UI.InlineCode> · 24
                小时半衰期 · 对比 6 小时前同一可比来源组
              </UI.Text>
              {data.roster.length ? (
                <ItemGroup>
                  {data.roster.map((source) => (
                    <Item
                      key={source.participant_key}
                      role="listitem"
                      className="px-0"
                    >
                      <ItemContent className="min-w-0 gap-2">
                        <UI.Text>
                          {source.source_name}
                          {source.first_party ? " · 一手来源" : ""}
                        </UI.Text>
                        <ItemDescription>
                          {source.mode === "editorial"
                            ? "编辑报道"
                            : "讨论信号"}
                          {source.tier ? ` · ${source.tier}` : ""} ·{" "}
                          {eventTime(source.source_time)}
                        </ItemDescription>
                        <UI.Text size="sm">
                          {source.title ?? "固定版本证据"}
                        </UI.Text>
                      </ItemContent>
                    </Item>
                  ))}
                </ItemGroup>
              ) : (
                <EventEmpty>尚未配置可参与计算的来源身份。</EventEmpty>
              )}
              {history.status === "ready" && history.data.length ? (
                <UI.Content
                  className="overflow-x-auto"
                  tabIndex={0}
                  role="region"
                  aria-label="小时热度明细"
                >
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>窗口结束</TableHead>
                        <TableHead>热度</TableHead>
                        <TableHead>参与者</TableHead>
                        <TableHead>覆盖</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {history.data.map((row) => (
                        <TableRow key={row.window_end}>
                          <TableCell>
                            <UI.InlineCode>
                              {eventTime(row.window_end)}
                            </UI.InlineCode>
                          </TableCell>
                          <TableCell>
                            <UI.InlineCode>
                              {row.participant_count
                                ? row.heat.toFixed(1)
                                : "待确定"}
                            </UI.InlineCode>
                          </TableCell>
                          <TableCell>
                            <UI.InlineCode>
                              {row.participant_count}
                            </UI.InlineCode>
                          </TableCell>
                          <TableCell>
                            {row.complete ? "完整" : "待补全"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </UI.Content>
              ) : null}
            </UI.Content>
          </CollapsibleContent>
        </Collapsible>
      ) : null}
    </UI.Content>
  );
}
