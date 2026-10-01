"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
              <TableHead>采集状态</TableHead>
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
                <TableCell>{coverageTime(row.due_at)}</TableCell>
                <TableCell>
                  <span className="block font-medium">{row.source_key}</span>
                  <span className="text-muted-foreground text-xs">
                    {capabilityLabel(row.capability)}
                  </span>
                </TableCell>
                <TableCell>
                  <div className="flex flex-col gap-2">
                    <p>{admissionLabel(row.admission_state)}</p>
                    <CoverageStatus row={row} />
                  </div>
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
          <Card
            key={row.window_id}
            aria-label={`${row.source_key} ${coverageTime(row.due_at)} 覆盖窗口`}
          >
            <CardHeader>
              <CardTitle asChild>
                <h3>
                  {row.source_key} · {capabilityLabel(row.capability)}
                </h3>
              </CardTitle>
              <CardDescription>{coverageTime(row.due_at)}</CardDescription>
              <CardAction>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => onSelect(row.window_id)}
                >
                  查看详情
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <p>{admissionLabel(row.admission_state)}</p>
              <CoverageStatus row={row} />
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
