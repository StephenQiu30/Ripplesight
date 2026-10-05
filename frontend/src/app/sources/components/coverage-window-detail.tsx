import * as UI from "@/components/ui/content";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

import {
  admissionLabel,
  capabilityLabel,
  coverageCount,
  coverageStatusLabel,
  coverageTime,
} from "./coverage-window-table";

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <UI.Content>
      <UI.Content as="dt" className="text-muted-foreground text-xs">
        {label}
      </UI.Content>
      <UI.Content as="dd" className="mt-1 text-sm font-medium wrap-break-word">
        {value}
      </UI.Content>
    </UI.Content>
  );
}

function version(value: number | null): string {
  return value === null ? "未知" : `v${value}`;
}

function RecordLinks({ row }: { row: HotKeyAPI.CollectionCoverageView }) {
  return (
    <UI.Content className="grid gap-5 sm:grid-cols-2">
      <UI.Content>
        <UI.Heading level={4} className="font-medium">
          入库内容
        </UI.Heading>
        {row.content_ids === null ? (
          <UI.Text className="text-muted-foreground mt-2 text-sm">未知</UI.Text>
        ) : row.content_ids.length === 0 ? (
          <UI.Text className="text-muted-foreground mt-2 text-sm">
            明确为 0 条
          </UI.Text>
        ) : (
          <ItemGroup className="mt-2 flex flex-col gap-2 text-sm">
            {row.content_ids.map((contentId) => (
              <Item role="listitem" variant="default" key={contentId}>
                <ItemContent className="min-w-0 gap-3">
                  <Button asChild variant="link" size="sm">
                    <Link href={`/content/${contentId}`}>
                      查看内容 {contentId.slice(0, 8)}
                    </Link>
                  </Button>
                </ItemContent>
              </Item>
            ))}
          </ItemGroup>
        )}
      </UI.Content>
      <UI.Content>
        <UI.Heading level={4} className="font-medium">
          热榜快照
        </UI.Heading>
        {row.snapshot_ids === null ? (
          <UI.Text className="text-muted-foreground mt-2 text-sm">未知</UI.Text>
        ) : row.snapshot_ids.length === 0 ? (
          <UI.Text className="text-muted-foreground mt-2 text-sm">
            明确为 0 个
          </UI.Text>
        ) : (
          <ItemGroup className="mt-2 flex flex-col gap-2 text-sm">
            {row.snapshot_ids.map((snapshotId) => (
              <Item role="listitem" variant="default" key={snapshotId}>
                <ItemContent className="min-w-0 gap-3">
                  <Button asChild variant="link" size="sm">
                    <Link
                      href={`/hotlists?source=${encodeURIComponent(row.source_key)}&snapshot=${encodeURIComponent(snapshotId)}`}
                    >
                      查看快照 {snapshotId.slice(0, 8)}
                    </Link>
                  </Button>
                </ItemContent>
              </Item>
            ))}
          </ItemGroup>
        )}
      </UI.Content>
    </UI.Content>
  );
}

export function CoverageWindowDetail({
  row,
  onClose,
}: {
  row: HotKeyAPI.CollectionCoverageView;
  onClose: () => void;
}) {
  return (
    <UI.Content
      as="section"
      id="coverage-detail"
      aria-labelledby="coverage-detail-heading"
      className="flex flex-col"
    >
      <UI.Content className="flex flex-wrap items-start justify-between gap-4">
        <UI.Content>
          <UI.Text className="text-muted-foreground text-xs tracking-wider uppercase">
            窗口详情
          </UI.Text>
          <UI.Heading
            level={3}
            id="coverage-detail-heading"
            className="mt-2 text-xl font-semibold"
          >
            {row.source_key} · {capabilityLabel(row.capability)}
          </UI.Heading>
          <UI.Text className="text-muted-foreground mt-2 text-sm">
            到期：{coverageTime(row.due_at)}（北京时间）
          </UI.Text>
        </UI.Content>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          关闭详情
        </Button>
      </UI.Content>
      <UI.Content className="mt-5 flex flex-wrap gap-2">
        <Badge variant="outline">{admissionLabel(row.admission_state)}</Badge>
        <Badge
          variant={
            row.coverage_status === "failed" ||
            row.coverage_status === "stopped"
              ? "destructive"
              : "secondary"
          }
        >
          {coverageStatusLabel(row.coverage_status)}
        </Badge>
        {row.gaps.length > 0 ? (
          <Badge variant="outline">{row.gaps.length} 段未确认缺口</Badge>
        ) : null}
      </UI.Content>
      {row.admission_reason || row.stop_reason ? (
        <UI.Content className="mt-5 flex flex-col gap-2 text-sm">
          {row.admission_reason ? (
            <UI.Text>受理原因：{row.admission_reason}</UI.Text>
          ) : null}
          {row.stop_reason ? (
            <UI.Text>停止原因：{row.stop_reason}</UI.Text>
          ) : null}
        </UI.Content>
      ) : null}
      {row.job_id === null ? (
        <UI.Text className="mt-5 text-sm font-medium">
          这个到期窗口没有关联 Job；窗口和缺口仍保留。
        </UI.Text>
      ) : (
        <Button asChild variant="secondary" size="sm" className="mt-5">
          <Link href={`/jobs/${row.job_id}`}>打开关联任务</Link>
        </Button>
      )}
      <UI.Content as="dl" className="mt-8 grid gap-x-6 gap-y-5 sm:grid-cols-2">
        <Fact label="窗口起点" value={coverageTime(row.window_start)} />
        <Fact label="窗口终点" value={coverageTime(row.window_end)} />
        <Fact
          label="当前连接版本"
          value={version(row.current_connection_version)}
        />
        <Fact
          label="Job 固定连接版本"
          value={version(row.job_connection_version)}
        />
        <Fact label="首次开始" value={coverageTime(row.started_at)} />
        <Fact label="结束" value={coverageTime(row.finished_at)} />
        <Fact label="最近成功" value={coverageTime(row.last_success_at)} />
        <Fact label="终态依据" value={row.terminal_evidence ?? "未知"} />
        <Fact label="实际请求" value={coverageCount(row.request_count)} />
        <Fact
          label="请求尝试"
          value={coverageCount(row.request_attempt_count)}
        />
        <Fact label="采集页数" value={coverageCount(row.page_count)} />
        <Fact label="观察条数" value={coverageCount(row.observed_count)} />
        <Fact label="入库条数" value={coverageCount(row.inserted_count)} />
        <Fact label="去重条数" value={coverageCount(row.deduplicated_count)} />
        <Fact label="关联 Job 状态" value={row.job_status ?? "未知"} />
        <Fact label="主题 ID" value={row.topic_id ?? "未知"} />
      </UI.Content>
      <UI.Content className="mt-8 grid gap-8 sm:grid-cols-2">
        <UI.Content>
          <UI.Heading level={4} className="font-medium">
            任务尝试
          </UI.Heading>
          {row.attempts === null ? (
            <UI.Text className="text-muted-foreground mt-2 text-sm">
              未知
            </UI.Text>
          ) : row.attempts.length === 0 ? (
            <UI.Text className="text-muted-foreground mt-2 text-sm">
              明确为 0 次
            </UI.Text>
          ) : (
            <ItemGroup className="mt-3 flex flex-col gap-2 text-sm">
              {row.attempts.map((attempt) => (
                <Item
                  role="listitem"
                  variant="default"
                  key={attempt.attempt_id}
                >
                  <ItemContent className="min-w-0 gap-3">
                    周期 {attempt.collection_cycle_no} ·{" "}
                    {coverageTime(attempt.started_at)} →{" "}
                    {coverageTime(attempt.finished_at)} ·{" "}
                    {attempt.outcome ?? "结果未知"}
                  </ItemContent>
                </Item>
              ))}
            </ItemGroup>
          )}
        </UI.Content>
        <UI.Content>
          <UI.Heading level={4} className="font-medium">
            分析状态
          </UI.Heading>
          {row.analysis === null ? (
            <UI.Text className="text-muted-foreground mt-2 text-sm">
              未知
            </UI.Text>
          ) : (
            <UI.Text className="mt-2 text-sm">
              待处理 {coverageCount(row.analysis.pending_count)} · 失败{" "}
              {coverageCount(row.analysis.failed_count)} · 标注异常{" "}
              {coverageCount(row.analysis.invalid_count)} · 有效{" "}
              {coverageCount(row.analysis.valid_count)}
            </UI.Text>
          )}
        </UI.Content>
      </UI.Content>
      <UI.Content className="mt-8 grid gap-8 sm:grid-cols-2">
        <UI.Content>
          <UI.Heading level={4} className="font-medium">
            资源预算
          </UI.Heading>
          {row.budgets === null ? (
            <UI.Text className="text-muted-foreground mt-2 text-sm">
              未知
            </UI.Text>
          ) : row.budgets.length === 0 ? (
            <UI.Text className="text-muted-foreground mt-2 text-sm">
              明确为 0 项
            </UI.Text>
          ) : (
            <ItemGroup className="mt-3 flex flex-col gap-3 text-sm">
              {row.budgets.map((budget) => (
                <Item
                  role="listitem"
                  variant="default"
                  key={`${budget.budget_key}:${budget.policy_version}`}
                >
                  <ItemContent className="min-w-0 gap-3">
                    <UI.Text as="span" className="font-medium">
                      {budget.budget_key} · v{budget.policy_version}
                    </UI.Text>
                    <UI.Text as="span" className="text-muted-foreground block">
                      上限 {budget.limit_units} · 预留 {budget.reserved_units} ·
                      实耗 {budget.consumed_units}
                    </UI.Text>
                  </ItemContent>
                </Item>
              ))}
            </ItemGroup>
          )}
        </UI.Content>
        <UI.Content>
          <UI.Heading level={4} className="font-medium">
            未确认缺口
          </UI.Heading>
          {row.gaps.length === 0 ? (
            <Empty className="mt-2">
              <EmptyHeader>
                <EmptyDescription>
                  暂无已记录缺口；覆盖结论仍以窗口状态为准。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ItemGroup className="mt-3 flex flex-col gap-3 text-sm">
              {row.gaps.map((gap, index) => (
                <Item
                  role="listitem"
                  variant="default"
                  key={`${gap.starts_at}:${index}`}
                >
                  <ItemContent className="min-w-0 gap-3">
                    {coverageTime(gap.starts_at)} → {coverageTime(gap.ends_at)}
                    <UI.Text as="span" className="text-muted-foreground block">
                      原因：{gap.reason}
                    </UI.Text>
                  </ItemContent>
                </Item>
              ))}
            </ItemGroup>
          )}
        </UI.Content>
      </UI.Content>
      <UI.Content className="mt-8 flex flex-col gap-6">
        <Separator />
        <RecordLinks row={row} />
      </UI.Content>
    </UI.Content>
  );
}
