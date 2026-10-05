import * as UI from "@/components/ui/content";
import { AlertDescription, Alert } from "@/components/ui/alert";
import Link from "next/link";

import {
  evidenceDate,
  RunStamp,
  SourceStatus,
} from "@/components/leaderboard/reading-parts";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export function SourceReading({ data }: { data: HotKeyAPI.SourceDetailView }) {
  return (
    <UI.Content className="flex flex-col gap-y-10">
      <UI.Content as="header" className="flex max-w-3xl flex-col gap-y-4">
        <Link
          className="text-muted-foreground text-sm hover:underline"
          href="/leaderboard/sources"
        >
          ← 评测来源
        </Link>
        <UI.Heading
          level={1}
          className="text-3xl font-medium tracking-tight sm:text-4xl"
        >
          {data.full_name}
        </UI.Heading>
        <UI.Content className="flex flex-wrap items-center gap-3">
          <SourceStatus source={data.source} />
          <UI.Text as="span" className="text-muted-foreground text-sm">
            {data.source.operator}
            {data.area ? ` · ${data.area}` : ""}
          </UI.Text>
        </UI.Content>
        <UI.Text className="text-muted-foreground leading-7">
          {data.source.description}
        </UI.Text>
        <RunStamp run={data.run} />
        <UI.Text className="text-muted-foreground text-xs leading-6">
          用途、限制与许可说明来自 AIHOT 2026-09-26
          固定注册表，来源条款以官方现行说明为准。
        </UI.Text>
        {data.official_url ? (
          <UI.TextLink
            className="text-sm underline underline-offset-4"
            href={data.official_url}
            target="_blank"
            rel="noreferrer"
          >
            官方来源
          </UI.TextLink>
        ) : null}
      </UI.Content>
      <UI.Content
        as="section"
        className="grid gap-8 md:grid-cols-2"
        aria-label="来源用途与限制"
      >
        <UI.Content className="flex flex-col gap-y-3">
          <UI.Heading level={2} className="text-xl font-medium">
            测量什么
          </UI.Heading>
          <UI.Text className="text-muted-foreground leading-7">
            {data.what}
          </UI.Text>
          <UI.Heading level={2} className="pt-2 text-xl font-medium">
            如何使用
          </UI.Heading>
          <UI.Text className="text-muted-foreground leading-7">
            {data.usage}
          </UI.Text>
        </UI.Content>
        <UI.Content className="flex flex-col gap-y-3">
          <UI.Heading level={2} className="text-xl font-medium">
            限制与许可
          </UI.Heading>
          <UI.Text className="text-muted-foreground leading-7">
            {data.limits}
          </UI.Text>
          <UI.Text className="text-sm leading-6">
            数据许可：{data.license}
          </UI.Text>
          {data.attribution ? (
            <UI.Text className="text-muted-foreground text-sm leading-6">
              署名：{data.attribution}
            </UI.Text>
          ) : null}
        </UI.Content>
      </UI.Content>
      <UI.Content
        as="section"
        className="flex flex-col gap-y-5"
        aria-label="来源原始成绩"
      >
        <UI.Content className="flex flex-col gap-y-2">
          <UI.Heading level={2} className="text-xl font-medium">
            {data.system_rows ? "系统与代理配置成绩" : "来源原始成绩"}
          </UI.Heading>
          <UI.Text className="text-muted-foreground text-sm">
            上游时间 {evidenceDate(data.upstream_at)} · 本地同步{" "}
            {evidenceDate(data.synced_at)}
          </UI.Text>
          {data.rows_note ? (
            <UI.Text className="text-muted-foreground text-sm leading-6">
              {data.rows_note}
            </UI.Text>
          ) : null}
          {data.system_rows ? (
            <Alert role="note" className="p-4 leading-6">
              <AlertDescription>
                这些行包含代理或系统配置，仅供参考，不能直接当作基础模型能力排名。
              </AlertDescription>
            </Alert>
          ) : null}
        </UI.Content>
        {data.rows.length === 0 ? (
          <Alert role="note" className="p-6 leading-6">
            <AlertDescription>
              {data.collected
                ? "该来源不提供可公开展示的逐行明细。"
                : "尚未采集该来源的合资格证据。注册表说明不代表数据已可用。"}
            </AlertDescription>
          </Alert>
        ) : (
          <Table>
            <TableCaption>
              保留来源原排名与成绩；不重新排列为本站排名
            </TableCaption>
            <TableHeader className="[&_tr]:border-0">
              <TableRow className="border-0">
                <TableHead>原排名</TableHead>
                <TableHead>来源模型名称</TableHead>
                <TableHead>原始成绩</TableHead>
                <TableHead>配置与取舍</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((row, index) => (
                <TableRow
                  key={`${row.source_model_name}-${row.configuration_label}-${index}`}
                  className="border-0"
                >
                  <TableCell className="font-mono">
                    {row.source_rank ?? "—"}
                  </TableCell>
                  <TableCell className="min-w-44">
                    {row.model_slug ? (
                      <Link
                        className="font-medium hover:underline"
                        href={`/leaderboard/models/${row.model_slug}`}
                      >
                        {row.source_model_name}
                      </Link>
                    ) : (
                      <UI.Text as="span">{row.source_model_name}</UI.Text>
                    )}
                    {row.provider ? (
                      <UI.Text className="text-muted-foreground mt-1 text-xs">
                        {row.provider}
                      </UI.Text>
                    ) : null}
                  </TableCell>
                  <TableCell className="font-mono">{row.display}</TableCell>
                  <TableCell className="min-w-44">
                    <UI.Text className="text-sm">
                      {row.configuration_label}
                    </UI.Text>
                    {row.excluded ? (
                      <UI.Text className="text-muted-foreground mt-1 text-xs">
                        排除：{row.excluded}
                      </UI.Text>
                    ) : (
                      <Badge className="mt-1" variant="secondary">
                        {data.system_rows ? "参考配置" : "代表配置"}
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </UI.Content>
    </UI.Content>
  );
}
