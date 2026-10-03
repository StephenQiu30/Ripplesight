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
    <div className="flex flex-col gap-y-10">
      <header className="flex max-w-3xl flex-col gap-y-4">
        <Link
          className="text-muted-foreground text-sm hover:underline"
          href="/leaderboard/sources"
        >
          ← 评测来源
        </Link>
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
          {data.full_name}
        </h1>
        <div className="flex flex-wrap items-center gap-3">
          <SourceStatus source={data.source} />
          <span className="text-muted-foreground text-sm">
            {data.source.operator}
            {data.area ? ` · ${data.area}` : ""}
          </span>
        </div>
        <p className="text-muted-foreground leading-7">
          {data.source.description}
        </p>
        <RunStamp run={data.run} />
        <p className="text-muted-foreground text-xs leading-6">
          用途、限制与许可说明来自 AIHOT 2026-09-26
          固定注册表，来源条款以官方现行说明为准。
        </p>
        {data.official_url ? (
          <a
            className="text-sm underline underline-offset-4"
            href={data.official_url}
            target="_blank"
            rel="noreferrer"
          >
            官方来源
          </a>
        ) : null}
      </header>
      <section
        className="grid gap-8 md:grid-cols-2"
        aria-label="来源用途与限制"
      >
        <div className="flex flex-col gap-y-3">
          <h2 className="text-xl font-medium">测量什么</h2>
          <p className="text-muted-foreground leading-7">{data.what}</p>
          <h2 className="pt-2 text-xl font-medium">如何使用</h2>
          <p className="text-muted-foreground leading-7">{data.usage}</p>
        </div>
        <div className="flex flex-col gap-y-3">
          <h2 className="text-xl font-medium">限制与许可</h2>
          <p className="text-muted-foreground leading-7">{data.limits}</p>
          <p className="text-sm leading-6">数据许可：{data.license}</p>
          {data.attribution ? (
            <p className="text-muted-foreground text-sm leading-6">
              署名：{data.attribution}
            </p>
          ) : null}
        </div>
      </section>
      <section className="flex flex-col gap-y-5" aria-label="来源原始成绩">
        <div className="flex flex-col gap-y-2">
          <h2 className="text-xl font-medium">
            {data.system_rows ? "系统与代理配置成绩" : "来源原始成绩"}
          </h2>
          <p className="text-muted-foreground text-sm">
            上游时间 {evidenceDate(data.upstream_at)} · 本地同步{" "}
            {evidenceDate(data.synced_at)}
          </p>
          {data.rows_note ? (
            <p className="text-muted-foreground text-sm leading-6">
              {data.rows_note}
            </p>
          ) : null}
          {data.system_rows ? (
            <p className="bg-muted rounded-lg p-4 text-sm leading-6">
              这些行包含代理或系统配置，仅供参考，不能直接当作基础模型能力排名。
            </p>
          ) : null}
        </div>
        {data.rows.length === 0 ? (
          <p className="bg-muted/40 rounded-xl p-6 text-sm leading-6">
            {data.collected
              ? "该来源不提供可公开展示的逐行明细。"
              : "尚未采集该来源的合资格证据。注册表说明不代表数据已可用。"}
          </p>
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
                      <span>{row.source_model_name}</span>
                    )}
                    {row.provider ? (
                      <p className="text-muted-foreground mt-1 text-xs">
                        {row.provider}
                      </p>
                    ) : null}
                  </TableCell>
                  <TableCell className="font-mono">{row.display}</TableCell>
                  <TableCell className="min-w-44">
                    <p className="text-sm">{row.configuration_label}</p>
                    {row.excluded ? (
                      <p className="text-muted-foreground mt-1 text-xs">
                        排除：{row.excluded}
                      </p>
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
      </section>
    </div>
  );
}
