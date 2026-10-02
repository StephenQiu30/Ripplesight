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
    <main className="mx-auto max-w-6xl space-y-12 px-5 py-12 sm:px-8">
      <header className="space-y-5">
        <Link
          className="text-muted-foreground text-sm hover:underline"
          href="/leaderboard"
        >
          ← 模型榜
        </Link>
        <div className="flex items-center gap-3">
          <ModelMark model={data.model} />
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
            {data.model.name}
          </h1>
        </div>
        <p className="text-muted-foreground text-sm">
          {data.model.provider ?? "运营方未知"} · 发布日期{" "}
          {data.model.released_at ?? "未知"} · 上下文{" "}
          {data.context_window_tokens === null
            ? "未知"
            : `${data.context_window_tokens.toLocaleString("zh-CN")} token`}
        </p>
        <RunStamp run={data.run} />
        {data.historical ? (
          <p className="bg-muted rounded-lg p-4 text-sm leading-6">
            当前展示历史发布轮次；该模型已不在最新合资格模型中。证据、排名与汇率对应上面的历史轮次。
          </p>
        ) : null}
        {data.weights_url ? (
          <a
            className="text-sm underline underline-offset-4"
            href={data.weights_url}
            target="_blank"
            rel="noreferrer"
          >
            查看公开模型权重
          </a>
        ) : null}
      </header>
      <section
        className="grid gap-8 md:grid-cols-2"
        aria-label="模型排名和价格"
      >
        <div className="space-y-4">
          <h2 className="text-xl font-medium">排名与覆盖</h2>
          <div className="bg-muted/40 space-y-4 rounded-xl p-5">
            <p>
              综合榜{" "}
              <strong className="font-mono text-2xl">
                {data.overall.rank === null
                  ? "未入榜"
                  : `#${data.overall.rank}`}
              </strong>
              {data.overall.score !== null ? (
                <span className="ml-4">
                  支持指数{" "}
                  <span className="font-mono">
                    {data.overall.score.toFixed(1)}
                  </span>
                </span>
              ) : null}
            </p>
            <p className="text-muted-foreground text-sm">
              {data.metric_count}{" "}
              项证据；指数不是获胜概率，未入分类榜不代表能力较低。
            </p>
            {data.overall_stability ? (
              <p className="text-sm">
                独立证据重算排名 {data.overall_stability.from_rank}–
                {data.overall_stability.to_rank}；固定集合权重变动排名{" "}
                {data.overall_stability.fixed_from}–
                {data.overall_stability.fixed_to}；纯序数排名{" "}
                {data.overall_stability.ordinal_rank}。
                {data.overall_stability.unavailable > 0
                  ? ` ${data.overall_stability.unavailable} 个场景资格不足。`
                  : ""}
              </p>
            ) : null}
            <ul className="space-y-2 text-sm">
              {data.categories.map((category) => (
                <li key={category.key} className="flex justify-between gap-3">
                  <Link
                    className="hover:underline"
                    href={`/leaderboard/category/${category.key}`}
                  >
                    {category.name}
                  </Link>
                  <span className="font-mono">
                    {category.rank === null
                      ? "证据不足"
                      : `#${category.rank} · ${category.score?.toFixed(1) ?? "—"}`}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className="space-y-4">
          <h2 className="text-xl font-medium">官方 API 价格</h2>
          <div className="bg-muted/40 rounded-xl p-5">
            <OfficialPrice price={data.price} />
          </div>
          <p className="text-muted-foreground text-sm leading-6">
            已核对的公开标准价格，具体地区、批处理、阶梯或促销条件以官方说明为准。未知价格不填零，供应商价格不参与排名。
          </p>
        </div>
      </section>
      <section className="space-y-6" aria-label="测评证据">
        <div className="space-y-2">
          <h2 className="text-xl font-medium">逐项评测证据</h2>
          <p className="text-muted-foreground text-sm leading-6">
            保留来源原始成绩和配置，不用统一百分制冒充不同任务的测评精度。代表配置按事先规则选择，不挑最高测得分数。
          </p>
        </div>
        {data.evidence.length === 0 ? (
          <p className="text-muted-foreground">
            当前轮次没有可展示的逐项证据。
          </p>
        ) : (
          data.evidence.map((group) => (
            <div key={group.key} className="space-y-4">
              <h3 className="font-medium">{group.name}</h3>
              <div className="grid gap-4 md:grid-cols-2">
                {group.items.map((item) => (
                  <article
                    key={item.unit}
                    className="bg-muted/40 space-y-3 rounded-xl p-5"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <Link
                        className="font-medium hover:underline"
                        href={`/leaderboard/sources/${item.source_key}`}
                      >
                        {item.source_name}
                      </Link>
                      <strong className="font-mono text-xl">
                        {item.display}
                      </strong>
                    </div>
                    <p className="text-sm">
                      来源模型：{item.source_model_name}
                    </p>
                    <p className="text-muted-foreground text-sm">
                      配置 {item.configuration_label} · 原始排名{" "}
                      {item.source_rank ?? "未知"}
                    </p>
                    <p className="text-muted-foreground text-sm">
                      {item.selection_reason}
                    </p>
                    {item.carried_forward ? (
                      <Badge variant="secondary">同协议沿用</Badge>
                    ) : null}
                    <details className="text-muted-foreground text-xs leading-6">
                      <summary className="cursor-pointer">
                        查看证据时间与协议
                      </summary>
                      <dl className="mt-2 space-y-1">
                        <div>
                          <dt className="inline">上游时间：</dt>
                          <dd className="inline">
                            {evidenceDate(item.upstream_at)}
                          </dd>
                        </div>
                        <div>
                          <dt className="inline">本地验证：</dt>
                          <dd className="inline">
                            {evidenceDate(item.verified_at)}
                          </dd>
                        </div>
                        <div>
                          <dt className="inline">测评时间：</dt>
                          <dd className="inline">
                            {evidenceDate(item.measured_at)}
                          </dd>
                        </div>
                        <div>
                          <dt className="inline">协议：</dt>
                          <dd className="inline font-mono break-all">
                            {item.protocol}
                          </dd>
                        </div>
                        <div>
                          <dt className="inline">快照：</dt>
                          <dd className="inline font-mono break-all">
                            {item.snapshot_id}
                          </dd>
                        </div>
                      </dl>
                      {Object.keys(item.components).length > 0 ? (
                        <pre className="mt-2 overflow-x-auto rounded-md p-2 font-mono">
                          {JSON.stringify(item.components, null, 2)}
                        </pre>
                      ) : null}
                    </details>
                    {item.official_url ? (
                      <a
                        className="text-sm underline underline-offset-4"
                        href={item.official_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        官方测评来源
                      </a>
                    ) : null}
                  </article>
                ))}
              </div>
            </div>
          ))
        )}
      </section>
      {data.excluded.length > 0 || data.unmeasured.length > 0 ? (
        <section className="grid gap-8 md:grid-cols-2" aria-label="证据缺项">
          <div className="space-y-3">
            <h2 className="text-xl font-medium">被排除的证据</h2>
            <p className="text-muted-foreground text-sm">
              存在来源记录，但不符合当前配置或测评资格。
            </p>
            {data.excluded.length > 0 ? (
              <ul className="space-y-3">
                {data.excluded.map((item) => (
                  <li key={item.key} className="text-sm">
                    <Link
                      className="hover:underline"
                      href={`/leaderboard/sources/${item.key}`}
                    >
                      {item.name}
                    </Link>
                    <p className="text-muted-foreground mt-1">
                      {item.reason ?? "没有可使用的合资格代表配置"}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground text-sm">无已知排除记录。</p>
            )}
          </div>
          <div className="space-y-3">
            <h2 className="text-xl font-medium">尚无测评证据</h2>
            <p className="text-muted-foreground text-sm">
              没有已发布证据，不按零分计入，也不补中位分。
            </p>
            <ul className="space-y-2">
              {data.unmeasured.map((item) => (
                <li key={item.key} className="text-sm">
                  <Link
                    className="hover:underline"
                    href={`/leaderboard/sources/${item.key}`}
                  >
                    {item.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
      <section className="space-y-5" aria-label="相邻模型对比">
        <h2 className="text-xl font-medium">相邻模型的共同证据</h2>
        <p className="text-muted-foreground text-sm">
          仅比较双方都有的证据。净支持按本轮固定预算加权，不是胜率；来源数量不能代替独立运营方数量。
        </p>
        {data.comparisons.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            当前轮次没有可展示的相邻对比。
          </p>
        ) : (
          data.comparisons.map((comparison) => (
            <details
              key={comparison.model.slug}
              className="bg-muted/40 rounded-xl p-5"
            >
              <summary className="cursor-pointer text-sm">
                <span className="font-medium">
                  #{comparison.rank} {comparison.model.name}
                </span>
                <span className="text-muted-foreground ml-3">
                  {comparison.shared_count} 项共同证据 · 预算{" "}
                  {(comparison.shared_weight * 100).toFixed(1)}% · 净支持{" "}
                  {comparison.net.toFixed(4)}
                </span>
              </summary>
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
                      <TableCell className="font-mono">{row.mine}</TableCell>
                      <TableCell className="font-mono">{row.theirs}</TableCell>
                      <TableCell className="font-mono">
                        {(row.weight * 100).toFixed(1)}%
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </details>
          ))
        )}
      </section>
    </main>
  );
}
