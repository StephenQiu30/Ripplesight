import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import {
  admissionLabel,
  capabilityLabel,
  coverageCount,
  coverageStatusLabel,
  coverageTime,
} from "./coverage-window-table";

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="mt-1 text-sm font-medium wrap-break-word">{value}</dd>
    </div>
  );
}

function version(value: number | null): string {
  return value === null ? "未知" : `v${value}`;
}

function RecordLinks({ row }: { row: HotKeyAPI.CollectionCoverageView }) {
  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <div>
        <h4 className="font-medium">入库内容</h4>
        {row.content_ids === null ? (
          <p className="text-muted-foreground mt-2 text-sm">未知</p>
        ) : row.content_ids.length === 0 ? (
          <p className="text-muted-foreground mt-2 text-sm">明确为 0 条</p>
        ) : (
          <ul className="mt-2 space-y-2 text-sm">
            {row.content_ids.map((contentId) => (
              <li key={contentId}>
                <Link
                  className="text-primary underline-offset-4 hover:underline"
                  href={`/content/${contentId}`}
                >
                  查看内容 {contentId.slice(0, 8)}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h4 className="font-medium">热榜快照</h4>
        {row.snapshot_ids === null ? (
          <p className="text-muted-foreground mt-2 text-sm">未知</p>
        ) : row.snapshot_ids.length === 0 ? (
          <p className="text-muted-foreground mt-2 text-sm">明确为 0 个</p>
        ) : (
          <ul className="mt-2 space-y-2 text-sm">
            {row.snapshot_ids.map((snapshotId) => (
              <li key={snapshotId}>
                <Link
                  className="text-primary underline-offset-4 hover:underline"
                  href={`/hotlists?source=${encodeURIComponent(row.source_key)}&snapshot=${encodeURIComponent(snapshotId)}`}
                >
                  查看快照 {snapshotId.slice(0, 8)}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
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
    <section
      id="coverage-detail"
      aria-labelledby="coverage-detail-heading"
      className="bg-muted mt-8 scroll-mt-8 rounded-2xl p-5 sm:p-8"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-muted-foreground text-xs tracking-wider uppercase">
            窗口详情
          </p>
          <h3
            id="coverage-detail-heading"
            className="mt-2 text-xl font-semibold"
          >
            {row.source_key} · {capabilityLabel(row.capability)}
          </h3>
          <p className="text-muted-foreground mt-2 text-sm">
            到期：{coverageTime(row.due_at)}（北京时间）
          </p>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          关闭详情
        </Button>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
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
      </div>

      {row.admission_reason || row.stop_reason ? (
        <div className="mt-5 space-y-2 text-sm">
          {row.admission_reason ? (
            <p>受理原因：{row.admission_reason}</p>
          ) : null}
          {row.stop_reason ? <p>停止原因：{row.stop_reason}</p> : null}
        </div>
      ) : null}

      {row.job_id === null ? (
        <p className="mt-5 text-sm font-medium">
          这个到期窗口没有关联 Job；窗口和缺口仍保留。
        </p>
      ) : (
        <Button asChild variant="secondary" size="sm" className="mt-5">
          <Link href={`/jobs/${row.job_id}`}>打开关联任务</Link>
        </Button>
      )}

      <dl className="mt-8 grid gap-x-6 gap-y-5 sm:grid-cols-2 lg:grid-cols-4">
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
      </dl>

      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        <div>
          <h4 className="font-medium">任务尝试</h4>
          {row.attempts === null ? (
            <p className="text-muted-foreground mt-2 text-sm">未知</p>
          ) : row.attempts.length === 0 ? (
            <p className="text-muted-foreground mt-2 text-sm">明确为 0 次</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {row.attempts.map((attempt) => (
                <li key={attempt.attempt_id}>
                  周期 {attempt.collection_cycle_no} ·{" "}
                  {coverageTime(attempt.started_at)} →{" "}
                  {coverageTime(attempt.finished_at)} ·{" "}
                  {attempt.outcome ?? "结果未知"}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h4 className="font-medium">分析状态</h4>
          {row.analysis === null ? (
            <p className="text-muted-foreground mt-2 text-sm">未知</p>
          ) : (
            <p className="mt-2 text-sm">
              待处理 {coverageCount(row.analysis.pending_count)} · 失败{" "}
              {coverageCount(row.analysis.failed_count)} · 标注异常{" "}
              {coverageCount(row.analysis.invalid_count)} · 有效{" "}
              {coverageCount(row.analysis.valid_count)}
            </p>
          )}
        </div>
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        <div>
          <h4 className="font-medium">资源预算</h4>
          {row.budgets === null ? (
            <p className="text-muted-foreground mt-2 text-sm">未知</p>
          ) : row.budgets.length === 0 ? (
            <p className="text-muted-foreground mt-2 text-sm">明确为 0 项</p>
          ) : (
            <ul className="mt-3 space-y-3 text-sm">
              {row.budgets.map((budget) => (
                <li key={`${budget.budget_key}:${budget.policy_version}`}>
                  <span className="font-medium">
                    {budget.budget_key} · v{budget.policy_version}
                  </span>
                  <span className="text-muted-foreground block">
                    上限 {budget.limit_units} · 预留 {budget.reserved_units} ·
                    实耗 {budget.consumed_units}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h4 className="font-medium">未确认缺口</h4>
          {row.gaps.length === 0 ? (
            <p className="text-muted-foreground mt-2 text-sm">
              暂无已记录缺口；覆盖结论仍以窗口状态为准。
            </p>
          ) : (
            <ul className="mt-3 space-y-3 text-sm">
              {row.gaps.map((gap, index) => (
                <li key={`${gap.starts_at}:${index}`}>
                  {coverageTime(gap.starts_at)} → {coverageTime(gap.ends_at)}
                  <span className="text-muted-foreground block">
                    原因：{gap.reason}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="mt-8 border-t pt-6">
        <RecordLinks row={row} />
      </div>
    </section>
  );
}
