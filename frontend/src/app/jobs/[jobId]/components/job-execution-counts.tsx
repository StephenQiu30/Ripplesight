"use client";

import { CollectionIdentityCounts } from "@/components/collection/identity-counts";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import * as UI from "@/components/ui/content";
import { formatTime } from "../../components/job-presenters";

const outcomes = {
  expired: "租约过期",
  succeeded: "成功",
  cancelled: "已取消",
  delayed: "延后",
  failed: "失败",
};

/** Show explicit execution receipts without treating a budget cycle as a material delta. */
export function JobExecutionCounts({
  job,
}: {
  job: Pick<
    HotKeyAPI.JobStatusView,
    "collection_executions" | "collection_executions_has_more"
  >;
}) {
  const executions = job.collection_executions;
  return (
    <UI.Content
      as="section"
      aria-label="单轮执行差分"
      className="mt-10 flex min-w-0 flex-col gap-4"
    >
      <UI.Heading level={2}>单轮执行差分</UI.Heading>
      <UI.Text size="sm" tone="muted">
        每次实际领取为一执行轮；自动重试或租约恢复也开启新轮，同一预算周期可有多轮执行。仅统计明确归属本轮的保留观察，与此前观察比较，不由累计量相减。累计量与单轮分别读取，不相减或加总。
      </UI.Text>
      {executions == null ? (
        <UI.Text tone="muted">执行轮次记录未知，旧响应不推断为零轮。</UI.Text>
      ) : executions.length === 0 ? (
        <UI.Text tone="muted">
          尚无实际领取记录；排队与待重试不等于已经执行。
        </UI.Text>
      ) : (
        executions.map((execution, index) => (
          <Collapsible
            key={execution.execution_epoch}
            defaultOpen={index === 0}
          >
            <CollapsibleTrigger asChild>
              <Button
                variant="outline"
                className="h-auto max-w-full justify-start text-left whitespace-normal"
              >
                第 {execution.execution_epoch} 执行轮 · 预算周期{" "}
                {execution.collection_cycle_no} ·{" "}
                {execution.outcome ? outcomes[execution.outcome] : "尚未收尾"}
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <UI.Content className="mt-4 min-w-0">
                <UI.Heading level={3}>
                  第 {execution.execution_epoch} 执行轮计量
                </UI.Heading>
                <UI.Text size="sm" tone="muted" className="mt-2">
                  开始 {formatTime(execution.started_at)} ·{" "}
                  {execution.finished_at
                    ? `结束 ${formatTime(execution.finished_at)}`
                    : "尚未收尾，计量仍会变化"}
                </UI.Text>
                <UI.Text size="sm" tone="muted" className="mt-2">
                  失败、取消或过期仍保留已持久化部分。已记录上游返回仅包含提交页面，未记录或在途响应保持未知，不表示来源零结果或完整覆盖。重放保留原轮归属。
                </UI.Text>
                {execution.counts == null ? (
                  <UI.Text tone="muted" className="mt-4">
                    本轮缺少可靠归属，计量未知，不按时间或累计量倒填。
                  </UI.Text>
                ) : (
                  <CollectionIdentityCounts
                    row={execution.counts}
                    scope="execution"
                  />
                )}
              </UI.Content>
            </CollapsibleContent>
          </Collapsible>
        ))
      )}
      {job.collection_executions_has_more ? (
        <UI.Text size="sm" tone="muted">
          仅展示最近 20 执行轮，更早轮次未展示；不是全部执行历史。
        </UI.Text>
      ) : null}
    </UI.Content>
  );
}
