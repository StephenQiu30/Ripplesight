"use client";
import {
  TableHead,
  TableRow,
  TableHeader,
  TableCell,
  TableBody,
  Table,
} from "@/components/ui/table";
import { ChevronDownIcon } from "lucide-react";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ApiRequestError } from "@/request";
import { getEventHeat, listEventHeatHistory } from "@/api/shijian";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
const trends = {
  new: "新出现",
  up: "上升",
  down: "下降",
  flat: "持平",
  unknown: "趋势待确定",
};
const badges = { new: "首次出现", surge: "来源骤增", rising: "持续升温" };
export function EventHeat({ eventId }: { eventId: string }) {
  const [data, setData] = useState<HotKeyAPI.EventAttentionView | null>(null);
  const [history, setHistory] = useState<HotKeyAPI.EventAttentionView[]>([]);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([
      getEventHeat({ event_id: eventId }, { signal: controller.signal }),
      listEventHeatHistory(
        { event_id: eventId, limit: 48 },
        { signal: controller.signal },
      ),
    ])
      .then(([current, snapshots]) => {
        if (!controller.signal.aborted) {
          setData(current);
          setHistory(snapshots.items);
          setFailed(false);
        }
      })
      .catch((error: unknown) => {
        if (
          !controller.signal.aborted &&
          !(error instanceof ApiRequestError && error.kind === "cancelled")
        ) {
          setFailed(true);
          toast.error("热度读取失败，请重试。");
        }
      });
    return () => controller.abort();
  }, [eventId, retry]);
  return (
    <section className="mt-10" aria-labelledby="event-heat-heading">
      <h2 id="event-heat-heading" className="text-2xl font-medium">
        当前事件热度
      </h2>
      {failed ? (
        <div className="mt-4">
          <Alert>
            <AlertDescription>热度读取失败。</AlertDescription>
          </Alert>
          <Button
            variant="outline"
            onClick={() => setRetry((value) => value + 1)}
          >
            重试热度
          </Button>
        </div>
      ) : !data ? (
        <p className="text-muted-foreground mt-4" role="status">
          正在读取独立来源热度…
        </p>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap gap-3">
            <Badge variant="secondary">
              48 小时热度{" "}
              {data.participant_count ? data.heat.toFixed(1) : "待确定"}
            </Badge>
            <Badge variant="secondary">
              {data.participant_count} 个独立参与者
            </Badge>
            <Badge variant="secondary">
              {trends[data.trend]}
              {data.trend_pct != null
                ? ` ${data.trend_pct > 0 ? "+" : ""}${data.trend_pct.toFixed(1)}%`
                : ""}
            </Badge>
            {data.badges.map((value) => (
              <Badge key={value}>{badges[value]}</Badge>
            ))}
          </div>
          <p className="text-muted-foreground mt-4 leading-7">
            编辑来源 {data.editorial_participant_count} 个，讨论来源{" "}
            {data.signal_participant_count} 个。
            {data.eligible
              ? "满足热榜条件。"
              : "至少两个独立参与者且含一个编辑来源后进入热榜。"}
            {data.complete ? "" : " 部分来源尚未完成及时采集。"}
            {data.uncomparable_participant_count
              ? ` ${data.uncomparable_participant_count} 个参与者因新增或采集时钟不足未用于趋势比较。`
              : ""}
          </p>
          <p className="text-muted-foreground mt-2 text-sm">
            {data.formula_version} · 24 小时半衰期 · 对比 6 小时前同一可比来源组
          </p>
          {data.roster.length ? (
            <ul className="mt-4 grid gap-3 sm:grid-cols-2">
              {data.roster.map((source) => (
                <li
                  className="rounded-lg border p-4"
                  key={source.participant_key}
                >
                  <p className="font-medium">
                    {source.source_name}{" "}
                    {source.first_party ? "· 一手来源" : ""}
                  </p>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {source.mode === "editorial" ? "编辑报道" : "讨论信号"}
                    {source.tier ? ` · ${source.tier}` : ""} ·{" "}
                    {new Date(source.source_time).toLocaleString("zh-CN")}
                  </p>
                  <p className="mt-2 text-sm break-words">
                    {source.title ?? "固定版本证据"}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground mt-4">
              尚未配置可参与计算的来源身份。
            </p>
          )}
          {data.interaction ? (
            <div className="mt-6 rounded-lg border p-4">
              <p className="font-medium">
                互动热度{" "}
                {data.interaction.score == null
                  ? "待确定"
                  : data.interaction.score.toFixed(2)}
              </p>
              <p className="text-muted-foreground mt-2 text-sm">
                按赞、评、转、浏览计算独立指标，未知值保留。
                {data.interaction.rising_state === "insufficient"
                  ? "真实历史样本不足，暂不判断升温。"
                  : data.interaction.rising_state === "rising"
                    ? "近期互动增量达到基线三倍。"
                    : "近期互动保持平稳。"}
              </p>
            </div>
          ) : null}
          <Collapsible className="mt-6">
            <CollapsibleTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
              >
                <span className="min-w-0 text-left">
                  小时热度历史（{history.length}）
                </span>
                <ChevronDownIcon
                  aria-hidden="true"
                  data-icon="inline-end"
                  className="group-data-[state=open]:rotate-180"
                />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent
              forceMount
              className="data-[state=closed]:hidden"
            >
              {history.length ? (
                <div className="mt-3 overflow-x-auto">
                  <Table className="w-full text-sm">
                    <TableHeader>
                      <TableRow className="border-b text-left">
                        <TableHead className="py-2">窗口结束</TableHead>
                        <TableHead>热度</TableHead>
                        <TableHead>参与者</TableHead>
                        <TableHead>覆盖</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {history.map((row) => (
                        <TableRow key={row.window_end} className="border-b">
                          <TableCell className="py-2 whitespace-nowrap">
                            {new Date(row.window_end).toLocaleString("zh-CN")}
                          </TableCell>
                          <TableCell>{row.heat.toFixed(1)}</TableCell>
                          <TableCell>{row.participant_count}</TableCell>
                          <TableCell>
                            {row.complete ? "完整" : "待补全"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <p className="text-muted-foreground mt-3 text-sm">
                  尚无当前修订的实际小时快照。
                </p>
              )}
            </CollapsibleContent>
          </Collapsible>
        </>
      )}
    </section>
  );
}
