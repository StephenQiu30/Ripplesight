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
    <main className="mx-auto max-w-6xl space-y-10 px-5 py-12 sm:px-8">
      <header className="max-w-3xl space-y-4">
        <p className="text-muted-foreground text-sm">模型榜</p>
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
          计算规则与证据边界
        </h1>
        <p className="text-muted-foreground leading-7">
          公开来源先形成成对偏好，再通过加权不完整 Kemeny
          求解全局顺序。跨来源原始分数不可直接求均值，缺项不补分。
        </p>
        <RunStamp run={data.run} />
        <p className="text-muted-foreground font-mono text-xs break-all">
          {data.methodology_version} · {data.display_method}
        </p>
      </header>
      <section className="max-w-3xl space-y-4">
        <h2 className="text-xl font-medium">怎样理解排名和指数</h2>
        <p className="text-muted-foreground leading-7">
          每项证据只比较双方均已测评的配置。有标准误或置信区间时使用正态分布软支持；没有误差信息时只使用原始高低顺序。排序使违反来源偏好的加权代价最小，采用整数规划和明确的最优性边界。
        </p>
        <p className="text-muted-foreground leading-7">
          页面指数来自累计 Kemeny
          排序支持相对固定锚点的映射。它用于阅读顺序，不能解释为能力差距、百分位或校准胜率。删掉单运营方/证据和调整权重的重算用于显示排名敏感性，不构成统计置信区间。
        </p>
        <details className="text-muted-foreground text-sm">
          <summary className="cursor-pointer">实际运行时定义</summary>
          <p className="mt-3 break-all">{data.score_definition}</p>
          <p className="mt-2 font-mono break-all">
            平手规则：{data.tie_policy}
          </p>
        </details>
      </section>
      <section className="space-y-4">
        <h2 className="text-xl font-medium">固定预算</h2>
        <p className="text-muted-foreground text-sm leading-6">
          总预算保持固定。来源停用或模型缺少某项时，该份额空缺，不转给其他证据。同机构、同家族不因为拆成多张榜就获得更多独立资格。
        </p>
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
                  <div className="flex flex-wrap gap-x-4 gap-y-2">
                    {budget.sources.map((source) => (
                      <Link
                        key={source}
                        href={`/leaderboard/sources/${source}`}
                        className="text-muted-foreground text-xs underline underline-offset-4"
                      >
                        {source}
                      </Link>
                    ))}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
      <section className="grid gap-8 md:grid-cols-2">
        <div className="space-y-4">
          <h2 className="text-xl font-medium">配置与证据资格</h2>
          <p className="text-muted-foreground leading-7">
            配置政策{" "}
            <span className="font-mono text-sm">
              {data.configuration_policy}
            </span>
            ：按预定推理档位、第一方身份和名称规则选择代表配置，避免按本次最高成绩挑选。代理、脚手架、混合或其他不合资格配置保留排除原因。匿名模型不参与公开榜。
          </p>
          <p className="text-muted-foreground leading-7">
            模型发布窗口 {data.release_window_months} 个月。同协议证据最多沿用{" "}
            {data.carry_forward_days}{" "}
            天，明确的新排除不会被旧成绩覆盖。上游测评时间和本地验证时间分别保存，不拿抓取时间当发布日期。
          </p>
        </div>
        <div className="space-y-4">
          <h2 className="text-xl font-medium">发布与失败保留</h2>
          <p className="text-muted-foreground leading-7">
            综合榜至少 {data.overall_minimum_models} 个模型、
            {data.overall_minimum_anchors} 个固定锚点；分类榜至少{" "}
            {data.category_minimum_models} 个模型、
            {data.category_minimum_anchors}{" "}
            个锚点。公开榜还必须完成最优求解并保持比较网络连通。模型同时满足独立来源、家族、运营方、专业预算与直接锚点证据门槛。
          </p>
          <p className="text-muted-foreground leading-7">
            新轮次不满足资格或来源请求失败时保留最近有效发布。页面不会触发远程请求、计算或预算消费，筛选仅选取已发布模型并保留原排名。参考榜、价格与模型权重不进入共识分数。
          </p>
        </div>
      </section>
      <section className="space-y-4">
        <h2 className="text-xl font-medium">固定锚点</h2>
        <p className="text-muted-foreground text-sm">
          锚点用于稳定指数的比较基准，缺失锚点不自动换成当前榜首。
        </p>
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {data.anchors.map((anchor) => (
            <li
              key={anchor}
              className="bg-muted/40 rounded-md px-3 py-2 font-mono text-xs"
            >
              {anchor}
            </li>
          ))}
        </ul>
      </section>
      <p className="text-muted-foreground max-w-3xl text-sm leading-6">
        方法、配置与来源注册表移植自 AIHOT 固定代码版本，保留 MIT
        版权说明。来源成绩、商标、模型权重和许可分别受各来源条款约束；已注册或固定样本测试通过不代表当前供应商可用性已验证。
        <a
          className="ml-1 underline underline-offset-4"
          href="https://github.com/KKKKhazix/AIHOT/tree/035f7b7f6e26cf203562ddd6065ff7adc1bb0c07/packages/backend/src/leaderboard"
          target="_blank"
          rel="noreferrer"
        >
          查看上游方法
        </a>
      </p>
    </main>
  );
}
