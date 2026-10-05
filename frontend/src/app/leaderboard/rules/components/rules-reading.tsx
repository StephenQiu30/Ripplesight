import * as UI from "@/components/ui/content";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
import { ChevronDownIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import Link from "next/link";

import { RunStamp } from "@/components/leaderboard/reading-parts";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export function RulesReading({ data }: { data: HotKeyAPI.RulesView }) {
  return (
    <UI.Content className="flex flex-col gap-y-10">
      <UI.Content as="header" className="flex max-w-3xl flex-col gap-y-4">
        <UI.Text className="text-muted-foreground text-sm">模型榜</UI.Text>
        <UI.Heading
          level={1}
          className="text-3xl font-medium tracking-tight sm:text-4xl"
        >
          计算规则与证据边界
        </UI.Heading>
        <UI.Text className="text-muted-foreground leading-7">
          公开来源先形成成对偏好，再通过加权不完整 Kemeny
          求解全局顺序。跨来源原始分数不可直接求均值，缺项不补分。
        </UI.Text>
        <RunStamp run={data.run} />
        <UI.Text className="text-muted-foreground font-mono text-xs break-all">
          {data.methodology_version} · {data.display_method}
        </UI.Text>
      </UI.Content>
      <UI.Content as="section" className="flex max-w-3xl flex-col gap-y-4">
        <UI.Heading level={2} className="text-xl font-medium">
          怎样理解排名和指数
        </UI.Heading>
        <UI.Text className="text-muted-foreground leading-7">
          每项证据只比较双方均已测评的配置。有标准误或置信区间时使用正态分布软支持；没有误差信息时只使用原始高低顺序。排序使违反来源偏好的加权代价最小，采用整数规划和明确的最优性边界。
        </UI.Text>
        <UI.Text className="text-muted-foreground leading-7">
          页面指数来自累计 Kemeny
          排序支持相对固定锚点的映射。它用于阅读顺序，不能解释为能力差距、百分位或校准胜率。删掉单运营方/证据和调整权重的重算用于显示排名敏感性，不构成统计置信区间。
        </UI.Text>
        <Collapsible className="text-muted-foreground text-sm">
          <CollapsibleTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              className="group h-auto w-full justify-between gap-2 px-0 whitespace-normal"
            >
              <UI.Text as="span" className="min-w-0 text-left">
                实际运行时定义
              </UI.Text>
              <ChevronDownIcon
                aria-hidden="true"
                data-icon="inline-end"
                className="group-data-[state=open]:rotate-180"
              />
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent forceMount className="data-[state=closed]:hidden">
            <UI.Text className="mt-3 break-all">
              {data.score_definition}
            </UI.Text>
            <UI.Text className="mt-2 font-mono break-all">
              平手规则：{data.tie_policy}
            </UI.Text>
          </CollapsibleContent>
        </Collapsible>
      </UI.Content>
      <UI.Content as="section" className="flex flex-col gap-y-4">
        <UI.Heading level={2} className="text-xl font-medium">
          固定预算
        </UI.Heading>
        <UI.Text className="text-muted-foreground text-sm leading-6">
          总预算保持固定。来源停用或模型缺少某项时，该份额空缺，不转给其他证据。同机构、同家族不因为拆成多张榜就获得更多独立资格。
        </UI.Text>
        <Table>
          <TableHeader className="[&_tr]:border-0">
            <TableRow className="border-0">
              <TableHead>能力预算</TableHead>
              <TableHead>权重</TableHead>
              <TableHead>证据来源</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.budgets.map((budget) => (
              <TableRow key={budget.key} className="border-0">
                <TableCell>{budget.name}</TableCell>
                <TableCell className="font-mono">
                  {(budget.weight * 100).toFixed(0)}%
                </TableCell>
                <TableCell>
                  <UI.Content className="flex flex-wrap gap-x-4 gap-y-2">
                    {budget.sources.map((source) => (
                      <Link
                        key={source}
                        href={`/leaderboard/sources/${source}`}
                        className="text-muted-foreground text-xs underline underline-offset-4"
                      >
                        {source}
                      </Link>
                    ))}
                  </UI.Content>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </UI.Content>
      <UI.Content as="section" className="grid gap-8 md:grid-cols-2">
        <UI.Content className="flex flex-col gap-y-4">
          <UI.Heading level={2} className="text-xl font-medium">
            配置与证据资格
          </UI.Heading>
          <UI.Text className="text-muted-foreground leading-7">
            配置政策{" "}
            <UI.Text as="span" className="font-mono text-sm">
              {data.configuration_policy}
            </UI.Text>
            ：按预定推理档位、第一方身份和名称规则选择代表配置，避免按本次最高成绩挑选。代理、脚手架、混合或其他不合资格配置保留排除原因。匿名模型不参与公开榜。
          </UI.Text>
          <UI.Text className="text-muted-foreground leading-7">
            模型发布窗口 {data.release_window_months} 个月。同协议证据最多沿用{" "}
            {data.carry_forward_days}{" "}
            天，明确的新排除不会被旧成绩覆盖。上游测评时间和本地验证时间分别保存，不拿抓取时间当发布日期。
          </UI.Text>
        </UI.Content>
        <UI.Content className="flex flex-col gap-y-4">
          <UI.Heading level={2} className="text-xl font-medium">
            发布与失败保留
          </UI.Heading>
          <UI.Text className="text-muted-foreground leading-7">
            综合榜至少 {data.overall_minimum_models} 个模型、
            {data.overall_minimum_anchors} 个固定锚点；分类榜至少{" "}
            {data.category_minimum_models} 个模型、
            {data.category_minimum_anchors}{" "}
            个锚点。公开榜还必须完成最优求解并保持比较网络连通。模型同时满足独立来源、家族、运营方、专业预算与直接锚点证据门槛。
          </UI.Text>
          <UI.Text className="text-muted-foreground leading-7">
            新轮次不满足资格或来源请求失败时保留最近有效发布。页面不会触发远程请求、计算或预算消费，筛选仅选取已发布模型并保留原排名。参考榜、价格与模型权重不进入共识分数。
          </UI.Text>
        </UI.Content>
      </UI.Content>
      <UI.Content as="section" className="flex flex-col gap-y-4">
        <UI.Heading level={2} className="text-xl font-medium">
          固定锚点
        </UI.Heading>
        <UI.Text className="text-muted-foreground text-sm">
          锚点用于稳定指数的比较基准，缺失锚点不自动换成当前榜首。
        </UI.Text>
        <ItemGroup className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {data.anchors.map((anchor) => (
            <Item
              role="listitem"
              variant="muted"
              key={anchor}
              className="px-3 py-2 font-mono"
            >
              <ItemContent className="min-w-0 gap-3">{anchor}</ItemContent>
            </Item>
          ))}
        </ItemGroup>
      </UI.Content>
      <UI.Text className="text-muted-foreground max-w-3xl text-sm leading-6">
        方法、配置与来源注册表移植自 AIHOT 固定代码版本，保留 MIT
        版权说明。来源成绩、商标、模型权重和许可分别受各来源条款约束；已注册或固定样本测试通过不代表当前供应商可用性已验证。
        <UI.TextLink
          className="ml-1 underline underline-offset-4"
          href="https://github.com/KKKKhazix/AIHOT/tree/035f7b7f6e26cf203562ddd6065ff7adc1bb0c07/packages/backend/src/leaderboard"
          target="_blank"
          rel="noreferrer"
        >
          查看上游方法
        </UI.TextLink>
      </UI.Text>
    </UI.Content>
  );
}
