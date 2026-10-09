import { PageHeader } from "@/components/system/page-header";
import * as UI from "@/components/ui/content";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import {
  Item,
  ItemContent,
  ItemGroup,
  ItemDescription,
} from "@/components/ui/item";
import { AlertDescription, Alert } from "@/components/ui/alert";
import { ChevronDownIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import { PageState } from "@/components/system/page-state";
import {
  evidenceDate,
  ModelMark,
  OfficialPrice,
  RunStamp,
  ScoreSupport,
} from "@/components/leaderboard/reading-parts";
import { Badge } from "@/components/ui/badge";
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

export function ModelReading({ data }: { data: HotKeyAPI.ModelDetailView }) {
  return (
    <UI.Content className="flex min-w-0 flex-col gap-8">
      <PageHeader
        title={
          <UI.Text as="span" className="flex min-w-0 items-center gap-3">
            <ModelMark model={data.model} />
            <UI.Text as="span" className="min-w-0 break-words">
              {data.model.name}
            </UI.Text>
          </UI.Text>
        }
        description={
          <>
            {data.model.provider ?? "运营方未知"} · 发布日期{" "}
            {data.model.released_at ?? "未知"}
            {data.context_window_tokens === null
              ? null
              : ` · 上下文 ${data.context_window_tokens.toLocaleString("zh-CN")} token`}
          </>
        }
        breadcrumbs={[
          { label: "模型榜", href: "/leaderboard" },
          { label: "模型证据" },
        ]}
      >
        <RunStamp run={data.run} />
        {data.historical ? (
          <Alert role="note">
            <AlertDescription>
              当前展示历史发布轮次；该模型已不在最新合资格模型中。证据、排名与汇率对应上面的历史轮次。
            </AlertDescription>
          </Alert>
        ) : null}
        {data.weights_url ? (
          <UI.TextLink href={data.weights_url} target="_blank" rel="noreferrer">
            查看公开模型权重
          </UI.TextLink>
        ) : null}
      </PageHeader>
      <Separator />
      <UI.Content
        as="section"
        className="grid gap-8 md:grid-cols-2"
        aria-label="模型排名和价格"
      >
        <UI.Content className="flex min-w-0 flex-col gap-4">
          <UI.Heading level={2}>排名与覆盖</UI.Heading>
          <UI.Text>
            综合榜{" "}
            <UI.InlineCode>
              {data.overall.rank === null ? "未入榜" : `#${data.overall.rank}`}
            </UI.InlineCode>
          </UI.Text>
          {data.overall.score !== null ? (
            <UI.Content className="flex flex-col gap-2">
              <UI.Text size="sm">支持指数</UI.Text>
              <ScoreSupport score={data.overall.score} label="综合榜支持指数" />
            </UI.Content>
          ) : null}
          <UI.Text tone="muted" size="sm">
            {data.metric_count}{" "}
            项证据；指数不是获胜概率，未入分类榜不代表能力较低。
          </UI.Text>
          {data.overall_stability ? (
            <UI.Text size="sm">
              独立证据重算排名 {data.overall_stability.from_rank}–
              {data.overall_stability.to_rank}；固定集合权重变动排名{" "}
              {data.overall_stability.fixed_from}–
              {data.overall_stability.fixed_to}；纯序数排名{" "}
              {data.overall_stability.ordinal_rank}。
              {data.overall_stability.unavailable > 0
                ? ` ${data.overall_stability.unavailable} 个场景资格不足。`
                : ""}
            </UI.Text>
          ) : null}
          <ItemGroup role={data.categories.length ? "list" : "group"}>
            {data.categories.map((category) => (
              <Item role="listitem" key={category.key}>
                <ItemContent className="gap-2">
                  <UI.TextLink href={`/leaderboard/category/${category.key}`}>
                    {category.name}
                  </UI.TextLink>
                  <UI.Text size="sm">
                    <UI.InlineCode>
                      {category.rank === null
                        ? "证据不足"
                        : `#${category.rank} · ${category.score?.toFixed(1) ?? "—"}`}
                    </UI.InlineCode>
                  </UI.Text>
                </ItemContent>
              </Item>
            ))}
          </ItemGroup>
        </UI.Content>
        <UI.Content className="flex min-w-0 flex-col gap-4">
          <UI.Heading level={2}>官方 API 价格</UI.Heading>
          <OfficialPrice price={data.price} />
          <UI.Text tone="muted" size="sm">
            已核对的公开标准价格，具体地区、批处理、阶梯或促销条件以官方说明为准。未知价格不填零，供应商价格不参与排名。
          </UI.Text>
        </UI.Content>
      </UI.Content>
      <Separator />
      <UI.Content
        as="section"
        className="flex flex-col gap-4"
        aria-label="测评证据"
      >
        <UI.Heading level={2}>逐项评测证据</UI.Heading>
        <UI.Text tone="muted" size="sm">
          保留来源原始成绩和配置，不用统一百分制冒充不同任务的测评精度。代表配置按事先规则选择，不挑最高测得分数。
        </UI.Text>
        {data.evidence.length === 0 ? (
          <PageState
            headingLevel={2}
            state="empty"
            eyebrow="暂无证据"
            title="当前轮次没有可展示的逐项证据"
            description="排名与价格以当前发布轮次为准；可以查看评测来源的覆盖情况。"
            action={
              <Button asChild variant="secondary">
                <UI.TextLink href="/leaderboard/sources">
                  查看来源覆盖
                </UI.TextLink>
              </Button>
            }
          />
        ) : (
          data.evidence.map((group) => (
            <UI.Content key={group.key} className="flex flex-col gap-4">
              <UI.Heading level={3}>{group.name}</UI.Heading>
              <ItemGroup>
                {group.items.map((item) => (
                  <Item key={item.unit} asChild>
                    <UI.Content as="article" className="min-w-0">
                      <ItemContent className="min-w-0 gap-3">
                        <Separator />
                        <UI.Content className="flex flex-wrap items-start justify-between gap-3">
                          <UI.TextLink
                            href={`/leaderboard/sources/${item.source_key}`}
                          >
                            {item.source_name}
                          </UI.TextLink>
                          <UI.InlineCode>{item.display}</UI.InlineCode>
                        </UI.Content>
                        <UI.Text size="sm">
                          来源模型：{item.source_model_name}
                        </UI.Text>
                        <ItemDescription className="line-clamp-none">
                          配置 {item.configuration_label} · 原始排名{" "}
                          {item.source_rank ?? "未知"}
                        </ItemDescription>
                        <ItemDescription className="line-clamp-none">
                          {item.selection_reason}
                        </ItemDescription>
                        {item.carried_forward ? (
                          <Badge variant="secondary">同协议沿用</Badge>
                        ) : null}
                        <Collapsible>
                          <CollapsibleTrigger asChild>
                            <Button type="button" variant="ghost" size="sm">
                              查看证据时间与协议
                              <ChevronDownIcon
                                aria-hidden="true"
                                data-icon="inline-end"
                              />
                            </Button>
                          </CollapsibleTrigger>
                          <CollapsibleContent
                            forceMount
                            className="data-[state=closed]:hidden"
                          >
                            <UI.Content
                              as="dl"
                              className="mt-3 flex flex-col gap-2"
                            >
                              <UI.Content>
                                <UI.Content as="dt">上游时间：</UI.Content>
                                <UI.Content as="dd">
                                  <UI.Text size="xs">
                                    {evidenceDate(item.upstream_at)}
                                  </UI.Text>
                                </UI.Content>
                              </UI.Content>
                              <UI.Content>
                                <UI.Content as="dt">本地验证：</UI.Content>
                                <UI.Content as="dd">
                                  <UI.Text size="xs">
                                    {evidenceDate(item.verified_at)}
                                  </UI.Text>
                                </UI.Content>
                              </UI.Content>
                              <UI.Content>
                                <UI.Content as="dt">测评时间：</UI.Content>
                                <UI.Content as="dd">
                                  <UI.Text size="xs">
                                    {evidenceDate(item.measured_at)}
                                  </UI.Text>
                                </UI.Content>
                              </UI.Content>
                              <UI.Content>
                                <UI.Content as="dt">协议：</UI.Content>
                                <UI.Content as="dd">
                                  <UI.InlineCode className="break-all">
                                    {item.protocol}
                                  </UI.InlineCode>
                                </UI.Content>
                              </UI.Content>
                              <UI.Content>
                                <UI.Content as="dt">快照：</UI.Content>
                                <UI.Content as="dd">
                                  <UI.InlineCode className="break-all">
                                    {item.snapshot_id}
                                  </UI.InlineCode>
                                </UI.Content>
                              </UI.Content>
                            </UI.Content>
                            {Object.keys(item.components).length > 0 ? (
                              <UI.CodeBlock className="mt-3 p-2">
                                {JSON.stringify(item.components, null, 2)}
                              </UI.CodeBlock>
                            ) : null}
                          </CollapsibleContent>
                        </Collapsible>
                        {item.official_url ? (
                          <UI.TextLink
                            href={item.official_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            官方测评来源
                          </UI.TextLink>
                        ) : null}
                      </ItemContent>
                    </UI.Content>
                  </Item>
                ))}
              </ItemGroup>
            </UI.Content>
          ))
        )}
      </UI.Content>
      {data.excluded.length > 0 || data.unmeasured.length > 0 ? (
        <UI.Content
          as="section"
          className="grid gap-8 md:grid-cols-2"
          aria-label="证据缺项"
        >
          <UI.Content className="flex flex-col gap-3">
            <UI.Heading level={2}>被排除的证据</UI.Heading>
            <UI.Text tone="muted" size="sm">
              存在来源记录，但不符合当前配置或测评资格。
            </UI.Text>
            {data.excluded.length > 0 ? (
              <ItemGroup>
                {data.excluded.map((item) => (
                  <Item role="listitem" key={item.key}>
                    <ItemContent className="gap-2">
                      <UI.TextLink href={`/leaderboard/sources/${item.key}`}>
                        {item.name}
                      </UI.TextLink>
                      <ItemDescription className="line-clamp-none">
                        {item.reason ?? "没有可使用的合资格代表配置"}
                      </ItemDescription>
                    </ItemContent>
                  </Item>
                ))}
              </ItemGroup>
            ) : (
              <Empty>
                <EmptyHeader>
                  <EmptyDescription>无已知排除记录。</EmptyDescription>
                </EmptyHeader>
              </Empty>
            )}
          </UI.Content>
          <UI.Content className="flex flex-col gap-3">
            <UI.Heading level={2}>尚无测评证据</UI.Heading>
            <UI.Text tone="muted" size="sm">
              没有已发布证据，不按零分计入，也不补中位分。
            </UI.Text>
            {data.unmeasured.length > 0 ? (
              <ItemGroup>
                {data.unmeasured.map((item) => (
                  <Item role="listitem" key={item.key}>
                    <ItemContent>
                      <UI.TextLink href={`/leaderboard/sources/${item.key}`}>
                        {item.name}
                      </UI.TextLink>
                    </ItemContent>
                  </Item>
                ))}
              </ItemGroup>
            ) : (
              <Empty>
                <EmptyHeader>
                  <EmptyDescription>无已知未测评来源。</EmptyDescription>
                </EmptyHeader>
              </Empty>
            )}
          </UI.Content>
        </UI.Content>
      ) : null}
      <Separator />
      <UI.Content
        as="section"
        className="flex min-w-0 flex-col gap-4"
        aria-label="相邻模型对比"
      >
        <UI.Heading level={2}>相邻模型的共同证据</UI.Heading>
        <UI.Text tone="muted" size="sm">
          仅比较双方都有的证据。净支持按本轮固定预算加权，不是胜率；来源数量不能代替独立运营方数量。
        </UI.Text>
        {data.comparisons.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyDescription>
                当前轮次没有可展示的相邻对比。
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          data.comparisons.map((comparison) => (
            <Collapsible key={comparison.model.slug} className="min-w-0">
              <UI.Content className="flex flex-col gap-3">
                <UI.Heading level={3}>
                  <UI.InlineCode>#{comparison.rank}</UI.InlineCode>{" "}
                  {comparison.model.name}
                </UI.Heading>
                <UI.Text tone="muted" size="sm">
                  {comparison.shared_count} 项共同证据 · 预算{" "}
                  <UI.InlineCode>
                    {(comparison.shared_weight * 100).toFixed(1)}%
                  </UI.InlineCode>{" "}
                  · 净支持{" "}
                  <UI.InlineCode>{comparison.net.toFixed(4)}</UI.InlineCode>
                </UI.Text>
                <CollapsibleTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="self-start"
                  >
                    查看共同证据
                    <ChevronDownIcon
                      aria-hidden="true"
                      data-icon="inline-end"
                    />
                  </Button>
                </CollapsibleTrigger>
              </UI.Content>
              <CollapsibleContent
                forceMount
                className="data-[state=closed]:hidden"
              >
                {comparison.has_page ? (
                  <UI.TextLink
                    className="mt-3 inline-block"
                    href={`/leaderboard/models/${comparison.model.slug}`}
                  >
                    查看 {comparison.model.name}
                  </UI.TextLink>
                ) : null}
                <Table className="mt-3 min-w-xl">
                  <TableCaption>双方均有的证据及本轮固定预算</TableCaption>
                  <TableHeader>
                    <TableRow>
                      <TableHead scope="col">来源</TableHead>
                      <TableHead scope="col">{data.model.name}</TableHead>
                      <TableHead scope="col">{comparison.model.name}</TableHead>
                      <TableHead scope="col">预算</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {comparison.rows.map((row, index) => (
                      <TableRow key={`${row.source_key}-${index}`}>
                        <TableCell>
                          <UI.TextLink
                            href={`/leaderboard/sources/${row.source_key}`}
                          >
                            {row.source_name}
                          </UI.TextLink>
                        </TableCell>
                        <TableCell>
                          <UI.InlineCode>{row.mine}</UI.InlineCode>
                        </TableCell>
                        <TableCell>
                          <UI.InlineCode>{row.theirs}</UI.InlineCode>
                        </TableCell>
                        <TableCell>
                          <UI.InlineCode>
                            {(row.weight * 100).toFixed(1)}%
                          </UI.InlineCode>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CollapsibleContent>
            </Collapsible>
          ))
        )}
      </UI.Content>
    </UI.Content>
  );
}
