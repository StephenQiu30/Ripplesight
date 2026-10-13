"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Content, Heading, Text } from "@/components/ui/content";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { publicationTime } from "./reading-format";

const labels: Record<HotKeyAPI.PublicPlatformTrend["state"], string> = {
  available: "可用",
  empty: "本次榜单为空",
  partial: "数据部分可用",
  stale: "榜单已过期",
  no_snapshot: "尚无采集快照",
  collecting: "正在采集",
  failed: "本次采集失败",
  not_configured: "未配置有效公开许可",
  unavailable: "来源或材料不可用",
};
const reasons: Record<string, string> = {
  permission_missing: "尚未确认整榜与条目的公开许可",
  permission_expired: "公开许可未生效或已过期",
  policy_changed: "来源准入已变化，公开许可需重新确认",
  source_unavailable: "来源准入、保留期或连接不可用",
  collection_skipped: "本次采集未获准执行",
  collection_pending: "等待本次采集完成",
  collection_failed: "本次采集未产生有效快照",
  snapshot_missing: "尚未保存有效采集结果",
  snapshot_stale: "超过已配置的展示时效",
  lifecycle_unavailable: "整榜或条目已撤回、到期或清理",
  provenance_unknown: "旧快照缺少准入依据",
  invalid: "快照依据校验未通过",
  source_changed: "采集连接已变化",
  truncated: "来源条目超过100条，本次仅保留前100条",
  source_time_unknown: "来源更新时间未知",
  native_rank_unknown: "平台原生名次未知",
  native_id_unknown: "平台原生条目标识未知",
  native_metric_unknown: "平台热度或计量单位未知",
};
const comparisons: Record<
  NonNullable<HotKeyAPI.PublicPlatformTrend["comparison_reason"]>,
  string
> = {
  comparable: "与相邻同口径快照比较",
  no_baseline: "缺少前次比较依据",
  gap: "采集有缺口，未比较排名",
  source_changed: "来源口径变化，未比较排名",
  unavailable: "前次依据不可用，未比较排名",
};

function Entries({ items }: { items: HotKeyAPI.PublicPlatformEntry[] }) {
  return items.map((item) => (
    <Content key={item.rank} layout="stack" className="min-w-0 gap-1">
      <Text size="sm" className="break-words">
        {item.rank}.{" "}
        <Link href={item.url} target="_blank" rel="noopener noreferrer">
          {item.title}
        </Link>
      </Text>
      <Text size="xs" tone="muted">
        原生名次 {item.native_rank ?? "未知"} · 热度 {item.heat ?? "未知"}{" "}
        {item.heat_unit ?? "单位未知"}
        {item.rank_delta == null
          ? " · 位置变化未知"
          : item.rank_delta === 0
            ? " · 位置持平"
            : ` · 订阅位置${item.rank_delta > 0 ? "上升" : "下降"}${Math.abs(item.rank_delta)}`}
      </Text>
    </Content>
  ));
}

/** Server-gated complete boards; UI expands the same fixed snapshot without refetching. */
export function PlatformTrends({
  boards,
  failure,
}: {
  boards?: HotKeyAPI.PublicPlatformTrend[];
  failure?: { status?: number };
}) {
  return (
    <Content
      as="section"
      aria-labelledby="home-platform-trends"
      layout="stack"
      className="min-w-0 gap-4"
    >
      <Heading level={2} appearance="sidebar" id="home-platform-trends">
        平台榜单
      </Heading>
      <Text size="xs" tone="muted">
        来源平台榜单经 RSSHub
        接入。序号为订阅条目位置；原生名次、热度和更新时间以来源提供为准。
      </Text>
      {failure ? (
        <Text size="sm" tone="muted">
          {[401, 403].includes(failure.status ?? 0)
            ? "无权读取平台榜单。"
            : "平台榜单读取失败，请刷新重试。"}
        </Text>
      ) : !boards?.length ? (
        <Text size="sm" tone="muted">
          尚未返回平台榜单依据。
        </Text>
      ) : (
        boards.map((board) => (
          <Content
            key={board.source_key}
            layout="stack"
            className="min-w-0 gap-2"
            aria-label={board.source_name}
          >
            <Heading level={3} appearance="sidebar">
              {board.source_name}
            </Heading>
            <Text size="sm">{labels[board.state]}</Text>
            {board.reasons?.length ? (
              <Text size="xs" tone="muted">
                {board.reasons
                  .map((reason) => reasons[reason] ?? "数据依据不足")
                  .join("；")}
              </Text>
            ) : null}
            {board.license_url && board.license_name ? (
              <Text size="xs" tone="muted">
                公开许可：
                <Link
                  href={board.license_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {board.license_name}
                </Link>{" "}
                · 确认 {publicationTime(board.permission_reviewed_at ?? null)} ·
                到期 {publicationTime(board.permission_expires_at ?? null)}
              </Text>
            ) : null}
            {board.observed_at ? (
              <Text size="xs" tone="muted">
                来源更新{" "}
                {board.source_updated_at
                  ? publicationTime(board.source_updated_at)
                  : "未知"}{" "}
                · 采集 {publicationTime(board.observed_at)} · 入库{" "}
                {publicationTime(board.received_at ?? null)} · 有效至{" "}
                {publicationTime(board.valid_until ?? null)}
              </Text>
            ) : null}
            {board.due_at ? (
              <Text size="xs" tone="muted">
                计划采集 {publicationTime(board.due_at)}
                {board.last_success_at && !board.observed_at
                  ? ` · 最近有效采集 ${publicationTime(board.last_success_at)}`
                  : ""}
              </Text>
            ) : null}
            {["available", "partial", "empty"].includes(board.state) ? (
              <>
                <Text size="xs" tone="muted">
                  保存 {board.entry_count ?? "未知"} / 来源{" "}
                  {board.source_entry_count ?? "未知"} 条 ·{" "}
                  {comparisons[board.comparison_reason ?? "no_baseline"]}
                </Text>
                <Entries items={(board.items ?? []).slice(0, 5)} />
                {(board.items?.length ?? 0) > 5 ? (
                  <Collapsible>
                    <CollapsibleTrigger asChild>
                      <Button variant="ghost" size="sm">
                        展开其余 {board.items!.length - 5} 条
                      </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <Content layout="stack" className="gap-3 py-2">
                        <Entries items={board.items!.slice(5)} />
                      </Content>
                    </CollapsibleContent>
                  </Collapsible>
                ) : null}
              </>
            ) : null}
          </Content>
        ))
      )}
    </Content>
  );
}
