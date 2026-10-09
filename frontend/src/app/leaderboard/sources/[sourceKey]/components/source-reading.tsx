import { PageHeader } from "@/components/system/page-header";
import * as UI from "@/components/ui/content";
import { AlertDescription, Alert } from "@/components/ui/alert";
import { PageState } from "@/components/system/page-state";
import {
  evidenceDate,
  RunStamp,
  SourceStatus,
} from "@/components/leaderboard/reading-parts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
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
    <UI.Content className="flex min-w-0 flex-col gap-8">
      <PageHeader
        title={data.full_name}
        description={data.source.description}
        breadcrumbs={[
          { label: "评测来源", href: "/leaderboard/sources" },
          { label: "评测来源明细" },
        ]}
      >
        <UI.Content className="flex flex-wrap items-center gap-3">
          <SourceStatus source={data.source} />
          <UI.Text as="span" tone="muted" size="sm">
            {data.source.operator}
            {data.area ? ` · ${data.area}` : ""}
          </UI.Text>
        </UI.Content>
        <RunStamp run={data.run} />
        <UI.Text tone="muted" size="xs">
          用途、限制与许可说明来自 AIHOT 2026-09-26
          固定注册表，来源条款以官方现行说明为准。
        </UI.Text>
        {data.official_url ? (
          <UI.TextLink
            href={data.official_url}
            target="_blank"
            rel="noreferrer"
          >
            官方来源
          </UI.TextLink>
        ) : null}
      </PageHeader>
      <Separator />
      <UI.Content
        as="section"
        className="grid gap-8 md:grid-cols-2"
        aria-label="来源用途与限制"
      >
        <UI.Content className="flex flex-col gap-3">
          <UI.Heading level={2}>测量什么</UI.Heading>
          <UI.Text tone="muted">{data.what}</UI.Text>
          <UI.Heading level={2} className="pt-2">
            如何使用
          </UI.Heading>
          <UI.Text tone="muted">{data.usage}</UI.Text>
        </UI.Content>
        <UI.Content className="flex flex-col gap-3">
          <UI.Heading level={2}>限制与许可</UI.Heading>
          <UI.Text tone="muted">{data.limits}</UI.Text>
          <UI.Text size="sm">数据许可：{data.license}</UI.Text>
          {data.attribution ? (
            <UI.Text tone="muted" size="sm">
              署名：{data.attribution}
            </UI.Text>
          ) : null}
        </UI.Content>
      </UI.Content>
      <Separator />
      <UI.Content
        as="section"
        className="flex min-w-0 flex-col gap-4"
        aria-label="来源原始成绩"
      >
        <UI.Heading level={2}>
          {data.system_rows ? "系统与代理配置成绩" : "来源原始成绩"}
        </UI.Heading>
        <UI.Text tone="muted" size="xs">
          上游时间 {evidenceDate(data.upstream_at)} · 本地同步{" "}
          {evidenceDate(data.synced_at)}
        </UI.Text>
        {data.rows_note ? (
          <UI.Text tone="muted" size="sm">
            {data.rows_note}
          </UI.Text>
        ) : null}
        {data.system_rows ? (
          <Alert role="note">
            <AlertDescription>
              这些行包含代理或系统配置，仅供参考，不能直接当作基础模型能力排名。
            </AlertDescription>
          </Alert>
        ) : null}
        {data.rows.length === 0 ? (
          <PageState
            headingLevel={2}
            state="empty"
            eyebrow="暂无明细"
            title={
              data.collected
                ? "该来源不提供可公开展示的逐行明细"
                : "尚未采集该来源的合资格证据"
            }
            description="注册表说明不代表数据已可用；可以查看其他来源的覆盖情况。"
            action={
              <Button asChild variant="secondary">
                <UI.TextLink href="/leaderboard/sources">
                  查看来源覆盖
                </UI.TextLink>
              </Button>
            }
          />
        ) : (
          <Table className="min-w-2xl">
            <TableCaption>
              保留来源原排名与成绩；不重新排列为本站排名
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">原排名</TableHead>
                <TableHead scope="col">来源模型名称</TableHead>
                <TableHead scope="col">原始成绩</TableHead>
                <TableHead scope="col">配置与取舍</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.rows.map((row, index) => (
                <TableRow
                  key={`${row.source_model_name}-${row.configuration_label}-${index}`}
                >
                  <TableCell>
                    <UI.InlineCode>{row.source_rank ?? "—"}</UI.InlineCode>
                  </TableCell>
                  <TableCell className="min-w-44">
                    <UI.Content className="flex flex-col gap-1">
                      {row.model_slug ? (
                        <UI.TextLink
                          href={`/leaderboard/models/${row.model_slug}`}
                        >
                          {row.source_model_name}
                        </UI.TextLink>
                      ) : (
                        <UI.Text as="span">{row.source_model_name}</UI.Text>
                      )}
                      {row.provider ? (
                        <UI.Text tone="muted" size="xs">
                          {row.provider}
                        </UI.Text>
                      ) : null}
                    </UI.Content>
                  </TableCell>
                  <TableCell>
                    <UI.InlineCode>{row.display}</UI.InlineCode>
                  </TableCell>
                  <TableCell className="min-w-44">
                    <UI.Content className="flex flex-col gap-1">
                      <UI.Text size="sm">{row.configuration_label}</UI.Text>
                      {row.excluded ? (
                        <UI.Text tone="muted" size="xs">
                          排除：{row.excluded}
                        </UI.Text>
                      ) : (
                        <Badge variant="secondary">
                          {data.system_rows ? "参考配置" : "代表配置"}
                        </Badge>
                      )}
                    </UI.Content>
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
