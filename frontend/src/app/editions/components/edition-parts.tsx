import * as UI from "@/components/ui/content";
import { Item, ItemContent } from "@/components/ui/item";
import Link from "next/link";
import { ApiRequestError } from "@/request";
import { Badge } from "@/components/ui/badge";

export const editionKinds = {
  daily: "日报",
  weekly: "周报",
  monthly: "月报",
} as const;

export const editionStates = {
  queued: "等待编选",
  running: "正在编选",
  complete: "已完成",
  partial: "部分完成",
  failed: "生成失败",
  unknown: "响应待核实",
  stale: "材料已变更",
} as const;

export function editionError(error: unknown): string {
  return error instanceof ApiRequestError
    ? `${error.message}${error.requestId ? ` · 请求编号 ${error.requestId}` : ""}`
    : "暂时无法读取刊期，请重试。";
}

export function EditionCard({ row }: { row: HotKeyAPI.EditionSummaryView }) {
  return (
    <Item
      role="listitem"
      variant="outline"
      className="flex flex-col gap-y-3 py-6"
    >
      <ItemContent className="min-w-0 gap-3">
        <UI.Content className="text-muted-foreground flex flex-wrap gap-3 text-xs">
          <UI.Text as="span">
            {editionKinds[row.kind]} · {row.key}
          </UI.Text>
          <Badge variant="outline">{editionStates[row.status]}</Badge>
          <UI.Text as="span">修订 {row.revision}</UI.Text>
        </UI.Content>
        <Link href={`/editions/${row.id}`} className="text-xl font-medium">
          {row.valid && row.title
            ? row.title
            : `${row.key} ${editionKinds[row.kind]}`}
        </Link>
        {row.valid && row.status === "complete" && (
          <UI.Text>
            <Link
              href={`/reports/${row.kind}/${row.key}`}
              className="text-primary text-sm underline-offset-4 hover:underline"
            >
              公开阅读
            </Link>
          </UI.Text>
        )}
      </ItemContent>
    </Item>
  );
}
