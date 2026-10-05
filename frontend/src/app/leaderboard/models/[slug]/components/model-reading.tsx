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
import Link from "next/link";

import {
  evidenceDate,
  ModelMark,
  OfficialPrice,
  RunStamp,
} from "@/components/leaderboard/reading-parts";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export function ModelReading({ data }: { data: HotKeyAPI.ModelDetailView }) {
  return (
    <UI.Content className="flex flex-col gap-y-12">
      <UI.Content as="header" className="flex flex-col gap-y-5">
        <Link
          className="text-muted-foreground text-sm hover:underline"
          href="/leaderboard"
        >
          ← 模型榜
        </Link>
        <UI.Content className="flex items-center gap-3">
          <ModelMark model={data.model} />
          <UI.Heading
            level={1}
            className="text-3xl font-medium tracking-tight sm:text-4xl"
          >
            {data.model.name}
          </UI.Heading>
        </UI.Content>
        <UI.Text className="text-muted-foreground text-sm">
          {data.model.provider ?? "运营方未知"} · 发布日期{" "}
          {data.model.released_at ?? "未知"} · 上下文{" "}
          {data.context_window_tokens === null
            ? "未知"
            : `${data.context_window_tokens.toLocaleString("zh-CN")} token`}
        </UI.Text>
        <RunStamp run={data.run} />
        {data.historical ? (
          <Alert role="note" className="p-4 leading-6">
            <AlertDescription>
              当前展示历史发布轮次；该模型已不在最新合资格模型中。证据、排名与汇率对应上面的历史轮次。
            </AlertDescription>
          </Alert>
        ) : null}
        {data.weights_url ? (
          <UI.TextLink
            className="text-sm underline underline-offset-4"
            href={data.weights_url}
            target="_blank"
            rel="noreferrer"
          >
            查看公开模型权重
          </UI.TextLink>
        ) : null}
      </UI.Content>
      <UI.Content
        as="section"
        className="grid gap-8 md:grid-cols-2"
        aria-label="模型排名和价格"
      >
        <UI.Content className="flex flex-col gap-y-4">
          <UI.Heading level={2} className="text-xl font-medium">
            排名与覆盖
          </UI.Heading>
          <Item variant="muted" asChild>
            <UI.Content className="flex flex-col gap-y-4 p-5">
              <ItemContent className="min-w-0 gap-3">
                <UI.Text>
                  综合榜{" "}
                  <UI.Text as="strong" className="font-mono text-2xl">
                    {data.overall.rank === null
                      ? "未入榜"
                      : `#${data.overall.rank}`}
                  </UI.Text>
                  {data.overall.score !== null ? (
                    <UI.Text as="span" className="ml-4">
                      支持指数{" "}
                      <UI.Text as="span" className="font-mono">
                        {data.overall.score.toFixed(1)}
                      </UI.Text>
                    </UI.Text>
                  ) : null}
                </UI.Text>
                <ItemDescription className="line-clamp-none">
                  {data.metric_count}{" "}
                  项证据；指数不是获胜概率，未入分类榜不代表能力较低。
                </ItemDescription>
                {data.overall_stability ? (
                  <UI.Text className="text-sm">
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
                <ItemGroup className="flex flex-col gap-y-2 text-sm">
                  {data.categories.map((category) => (
                    <Item
                      role="listitem"
                      variant="default"
                      key={category.key}
                      className="flex justify-between gap-3"
                    >
                      <ItemContent className="min-w-0 gap-3">
                        <Link
                          className="hover:underline"
                          href={`/leaderboard/category/${category.key}`}
                        >
                          {category.name}
                        </Link>
                        <UI.Text as="span" className="font-mono">
                          {category.rank === null
                            ? "证据不足"
                            : `#${category.rank} · ${category.score?.toFixed(1) ?? "—"}`}
                        </UI.Text>
                      </ItemContent>
                    </Item>
                  ))}
                </ItemGroup>
              </ItemContent>
            </UI.Content>
          </Item>
        </UI.Content>
        <UI.Content className="flex flex-col gap-y-4">
          <UI.Heading level={2} className="text-xl font-medium">
            官方 API 价格
          </UI.Heading>
          <Item variant="muted" asChild>
            <UI.Content className="p-5">
              <ItemContent className="min-w-0 gap-3">
                <OfficialPrice price={data.price} />
              </ItemContent>
            </UI.Content>
          </Item>
          <UI.Text className="text-muted-foreground text-sm leading-6">
            已核对的公开标准价格，具体地区、批处理、阶梯或促销条件以官方说明为准。未知价格不填零，供应商价格不参与排名。
          </UI.Text>
        </UI.Content>
      </UI.Content>
      <UI.Content
        as="section"
        className="flex flex-col gap-y-6"
        aria-label="测评证据"
      >
        <UI.Content className="flex flex-col gap-y-2">
          <UI.Heading level={2} className="text-xl font-medium">
            逐项评测证据
          </UI.Heading>
          <UI.Text className="text-muted-foreground text-sm leading-6">
            保留来源原始成绩和配置，不用统一百分制冒充不同任务的测评精度。代表配置按事先规则选择，不挑最高测得分数。
          </UI.Text>
        </UI.Content>
        {data.evidence.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyDescription>
                当前轮次没有可展示的逐项证据。
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          data.evidence.map((group) => (
            <UI.Content key={group.key} className="flex flex-col gap-y-4">
              <UI.Heading level={3} className="font-medium">
                {group.name}
              </UI.Heading>
              <UI.Content className="grid gap-4 md:grid-cols-2">
                {group.items.map((item) => (
                  <Item variant="muted" key={item.unit} asChild>
                    <UI.Content
                      as="article"
                      className="flex flex-col gap-y-3 p-5"
                    >
                      <ItemContent className="min-w-0 gap-3">
                        <UI.Content className="flex flex-wrap items-start justify-between gap-3">
                          <Link
                            className="font-medium hover:underline"
                            href={`/leaderboard/sources/${item.source_key}`}
                          >
                            {item.source_name}
                          </Link>
                          <UI.Text as="strong" className="font-mono text-xl">
                            {item.display}
                          </UI.Text>
                        </UI.Content>
                        <UI.Text className="text-sm">
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
                        <Collapsible className="text-muted-foreground text-xs leading-6">
                          <CollapsibleTrigger asChild>
                            <Button
                              type="button"
                              variant="ghost"
                              className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
                            >
                              <UI.Text as="span" className="min-w-0 text-left">
                                查看证据时间与协议
                              </UI.Text>
                              <ChevronDownIcon
                                aria-hidden="true"
                                data-icon="inline-end"
                                className="group-data-[state=open]:rotate-180"
                              />
                            </Button>
                          </CollapsibleTrigger>
                          <CollapsibleContent
                            forceMount
                            className="data-[state=closed]:hidden"
                          >
                            <UI.Content
                              as="dl"
                              className="mt-2 flex flex-col gap-y-1"
                            >
                              <UI.Content>
                                <UI.Content as="dt" className="inline">
                                  上游时间：
                                </UI.Content>
                                <UI.Content as="dd" className="inline">
                                  {evidenceDate(item.upstream_at)}
                                </UI.Content>
                              </UI.Content>
                              <UI.Content>
                                <UI.Content as="dt" className="inline">
                                  本地验证：
                                </UI.Content>
                                <UI.Content as="dd" className="inline">
                                  {evidenceDate(item.verified_at)}
                                </UI.Content>
                              </UI.Content>
                              <UI.Content>
                                <UI.Content as="dt" className="inline">
                                  测评时间：
                                </UI.Content>
                                <UI.Content as="dd" className="inline">
                                  {evidenceDate(item.measured_at)}
                                </UI.Content>
                              </UI.Content>
                              <UI.Content>
                                <UI.Content as="dt" className="inline">
                                  协议：
                                </UI.Content>
                                <UI.Content
                                  as="dd"
                                  className="inline font-mono break-all"
                                >
                                  {item.protocol}
                                </UI.Content>
                              </UI.Content>
                              <UI.Content>
                                <UI.Content as="dt" className="inline">
                                  快照：
                                </UI.Content>
                                <UI.Content
                                  as="dd"
                                  className="inline font-mono break-all"
                                >
                                  {item.snapshot_id}
                                </UI.Content>
                              </UI.Content>
                            </UI.Content>
                            {Object.keys(item.components).length > 0 ? (
                              <UI.CodeBlock className="mt-2 overflow-x-auto rounded-md p-2 font-mono">
                                {JSON.stringify(item.components, null, 2)}
                              </UI.CodeBlock>
                            ) : null}
                          </CollapsibleContent>
                        </Collapsible>
                        {item.official_url ? (
                          <UI.TextLink
                            className="text-sm underline underline-offset-4"
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
              </UI.Content>
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
          <UI.Content className="flex flex-col gap-y-3">
            <UI.Heading level={2} className="text-xl font-medium">
              被排除的证据
            </UI.Heading>
            <UI.Text className="text-muted-foreground text-sm">
              存在来源记录，但不符合当前配置或测评资格。
            </UI.Text>
            {data.excluded.length > 0 ? (
              <ItemGroup className="flex flex-col gap-y-3">
                {data.excluded.map((item) => (
                  <Item role="listitem" variant="default" key={item.key}>
                    <ItemContent className="min-w-0 gap-3">
                      <Link
                        className="hover:underline"
                        href={`/leaderboard/sources/${item.key}`}
                      >
                        {item.name}
                      </Link>
                      <ItemDescription className="mt-1 line-clamp-none">
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
          <UI.Content className="flex flex-col gap-y-3">
            <UI.Heading level={2} className="text-xl font-medium">
              尚无测评证据
            </UI.Heading>
            <UI.Text className="text-muted-foreground text-sm">
              没有已发布证据，不按零分计入，也不补中位分。
            </UI.Text>
            <ItemGroup className="flex flex-col gap-y-2">
              {data.unmeasured.map((item) => (
                <Item role="listitem" variant="default" key={item.key}>
                  <ItemContent className="min-w-0 gap-3">
                    <Link
                      className="hover:underline"
                      href={`/leaderboard/sources/${item.key}`}
                    >
                      {item.name}
                    </Link>
                  </ItemContent>
                </Item>
              ))}
            </ItemGroup>
          </UI.Content>
        </UI.Content>
      ) : null}
      <UI.Content
        as="section"
        className="flex flex-col gap-y-5"
        aria-label="相邻模型对比"
      >
        <UI.Heading level={2} className="text-xl font-medium">
          相邻模型的共同证据
        </UI.Heading>
        <UI.Text className="text-muted-foreground text-sm">
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
            <Item variant="muted" asChild key={comparison.model.slug}>
              <Collapsible className="p-5">
                <CollapsibleTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
                  >
                    <UI.Text as="span" className="min-w-0 text-left">
                      <UI.Text as="span" className="font-medium">
                        #{comparison.rank}
                        {comparison.model.name}
                      </UI.Text>
                      <UI.Text as="span" className="text-muted-foreground ml-3">
                        {comparison.shared_count} 项共同证据 · 预算{" "}
                        {(comparison.shared_weight * 100).toFixed(1)}% · 净支持{" "}
                        {comparison.net.toFixed(4)}
                      </UI.Text>
                    </UI.Text>
                    <ChevronDownIcon
                      aria-hidden="true"
                      data-icon="inline-end"
                      className="group-data-[state=open]:rotate-180"
                    />
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent
                  forceMount
                  className="data-[state=closed]:hidden"
                >
                  {comparison.has_page ? (
                    <Link
                      className="mt-3 inline-block text-sm underline underline-offset-4"
                      href={`/leaderboard/models/${comparison.model.slug}`}
                    >
                      查看 {comparison.model.name}
                    </Link>
                  ) : null}
                  <Table className="mt-3">
                    <TableHeader className="[&_tr]:border-0">
                      <TableRow className="border-0">
                        <TableHead>来源</TableHead>
                        <TableHead>{data.model.name}</TableHead>
                        <TableHead>{comparison.model.name}</TableHead>
                        <TableHead>预算</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {comparison.rows.map((row, index) => (
                        <TableRow
                          key={`${row.source_key}-${index}`}
                          className="border-0"
                        >
                          <TableCell>
                            <Link
                              className="hover:underline"
                              href={`/leaderboard/sources/${row.source_key}`}
                            >
                              {row.source_name}
                            </Link>
                          </TableCell>
                          <TableCell className="font-mono">
                            {row.mine}
                          </TableCell>
                          <TableCell className="font-mono">
                            {row.theirs}
                          </TableCell>
                          <TableCell className="font-mono">
                            {(row.weight * 100).toFixed(1)}%
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CollapsibleContent>
              </Collapsible>
            </Item>
          ))
        )}
      </UI.Content>
    </UI.Content>
  );
}
