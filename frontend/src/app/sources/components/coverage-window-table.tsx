"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const COVERAGE_LABELS: Record<
  HotKeyAPI.CollectionCoverageResultStatus,
  string
> = {
  pending: "待观察",
  not_attempted: "未尝试",
  complete: "已确认完成",
  empty: "已确认空结果",
  partial: "部分结果",
  failed: "失败",
  stopped: "已停止",
};

const ADMISSION_LABELS: Record<HotKeyAPI.DueAdmissionState, string> = {
  pending: "待受理",
  accepted: "已受理",
  skipped: "已跳过",
  missed: "错过到期",
};

const CAPABILITY_LABELS: Record<HotKeyAPI.SourceCapability, string> = {
  search: "检索",
  author_posts: "作者作品",
  comments: "评论",
  replies: "回复",
  page_content: "页面正文",
  hotlist: "热榜",
};

export function coverageStatusLabel(
  status: HotKeyAPI.CollectionCoverageResultStatus,
): string {
  return COVERAGE_LABELS[status];
}

export function admissionLabel(state: HotKeyAPI.DueAdmissionState): string {
  return ADMISSION_LABELS[state];
}

export function capabilityLabel(
  capability: HotKeyAPI.SourceCapability,
): string {
  return CAPABILITY_LABELS[capability];
}

export function coverageCount(value: number | null): string {
  return value === null ? "未知" : String(value);
}

export function coverageTime(value: string | null): string {
  if (value === null) return "未知";
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return "未知";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(timestamp);
}

function CoverageStatus({ row }: { row: HotKeyAPI.CollectionCoverageView }) {
  const variant =
    row.coverage_status === "failed" || row.coverage_status === "stopped"
      ? "destructive"
      : row.coverage_status === "complete" || row.coverage_status === "empty"
        ? "secondary"
        : "outline";
  return (
    <div className="flex flex-wrap gap-2">
      <Badge variant={variant}>
        {coverageStatusLabel(row.coverage_status)}
      </Badge>
      {row.gaps.length > 0 ? (
        <Badge variant="outline">{row.gaps.length} 段未确认缺口</Badge>
      ) : null}
    </div>
  );
}

export function CoverageWindowTable({
  items,
  selectedId,
  onSelect,
}: {
  items: HotKeyAPI.CollectionCoverageView[];
  selectedId: string | null;
  onSelect: (windowId: string) => void;
}) {
  return (
    <>
      <div className="mt-6 hidden md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>计划到期 · 北京时间</TableHead>
              <TableHead>来源 / 能力</TableHead>
              <TableHead>受理</TableHead>
              <TableHead>覆盖</TableHead>
              <TableHead className="text-right">请求 / 页</TableHead>
              <TableHead className="text-right">入库 / 去重</TableHead>
              <TableHead>
                <span className="sr-only">操作</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((row) => (
              <TableRow
                key={row.window_id}
                data-state={
                  row.window_id === selectedId ? "selected" : undefined
                }
              >
                <TableCell className="font-medium">
                  {coverageTime(row.due_at)}
                </TableCell>
                <TableCell>
                  <span className="block font-medium">{row.source_key}</span>
                  <span className="text-muted-foreground text-xs">
                    {capabilityLabel(row.capability)}
                  </span>
                </TableCell>
                <TableCell>{admissionLabel(row.admission_state)}</TableCell>
                <TableCell>
                  <CoverageStatus row={row} />
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {coverageCount(row.request_count)} /{" "}
                  {coverageCount(row.page_count)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {coverageCount(row.inserted_count)} /{" "}
                  {coverageCount(row.deduplicated_count)}
                </TableCell>
                <TableCell>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => onSelect(row.window_id)}
                    aria-label={`查看 ${row.source_key} ${coverageTime(row.due_at)} 的覆盖详情`}
                  >
                    查看
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="mt-6 grid gap-3 md:hidden">
        {items.map((row) => (
          <article
            key={row.window_id}
            className="bg-muted rounded-2xl p-5"
            aria-label={`${row.source_key} ${coverageTime(row.due_at)} 覆盖窗口`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-medium">
                  {row.source_key} · {capabilityLabel(row.capability)}
                </h3>
                <p className="text-muted-foreground mt-1 text-sm">
                  {coverageTime(row.due_at)}
                </p>
              </div>
              <CoverageStatus row={row} />
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-muted-foreground">受理</dt>
                <dd>{admissionLabel(row.admission_state)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">请求 / 页</dt>
                <dd>
                  {coverageCount(row.request_count)} /{" "}
                  {coverageCount(row.page_count)}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">入库</dt>
                <dd>{coverageCount(row.inserted_count)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">去重</dt>
                <dd>{coverageCount(row.deduplicated_count)}</dd>
              </div>
            </dl>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="mt-5"
              onClick={() => onSelect(row.window_id)}
            >
              查看详情
            </Button>
          </article>
        ))}
      </div>
    </>
  );
}
