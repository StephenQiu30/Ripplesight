import Link from "next/link";

import {
  ModelMark,
  OfficialPrice,
  RunStamp,
} from "@/components/leaderboard/reading-parts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export function BoardReading({
  data,
  domestic,
  openWeights,
}: {
  data: HotKeyAPI.BoardView;
  domestic: boolean;
  openWeights: boolean;
}) {
  const href =
    data.board.key === "overall"
      ? "/leaderboard"
      : `/leaderboard/category/${data.board.key}`;
  return (
    <div className="space-y-10">
      <header className="max-w-3xl space-y-4">
        <p className="text-muted-foreground text-sm">公开评测共识</p>
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
          {data.board.name}
        </h1>
        <p className="text-muted-foreground leading-7">
          {data.board.description}
        </p>
        <RunStamp run={data.run} />
      </header>
      <nav aria-label="模型榜分类" className="flex flex-wrap gap-2">
        {data.tabs.map((tab) => (
          <Button
            key={tab.key}
            variant={data.board.key === tab.key ? "secondary" : "ghost"}
            asChild
          >
            <Link
              href={tab.href}
              aria-current={data.board.key === tab.key ? "page" : undefined}
            >
              {tab.name}
            </Link>
          </Button>
        ))}
      </nav>
      <section
        className="bg-muted/40 space-y-3 rounded-xl p-5 sm:p-6"
        aria-label="榜单解读"
      >
        <p className="leading-7">{data.board.how_to_read}</p>
        <p className="text-muted-foreground text-sm leading-6">
          排名由加权 Kemeny
          共识决定，支持指数基于固定锚点。指数不是能力差距或获胜概率；缺失证据不补分、不重新分配预算。
        </p>
        <p className="text-muted-foreground text-sm">
          本轮 {data.board.model_count} 个合资格模型，{data.board.source_count}{" "}
          个来源、{data.board.operator_count} 个运营方。
        </p>
        <Link
          className="text-sm underline underline-offset-4"
          href="/leaderboard/rules"
        >
          阅读计算规则
        </Link>
      </section>
      <section className="space-y-5" aria-label="模型排名">
        <form
          action={href}
          method="get"
          className="flex flex-wrap items-center gap-4"
        >
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="domestic"
              value="true"
              defaultChecked={domestic}
              className="accent-foreground size-4"
            />
            国内模型
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="open_weights"
              value="true"
              defaultChecked={openWeights}
              className="accent-foreground size-4"
            />
            开放权重
          </label>
          <Button type="submit" variant="secondary" size="sm">
            应用筛选
          </Button>
          {domestic || openWeights ? (
            <Link
              className="text-muted-foreground text-sm underline underline-offset-4"
              href={href}
            >
              清除筛选
            </Link>
          ) : null}
        </form>
        <p className="text-muted-foreground text-sm">
          筛选保留原排名，最多展示 30 个模型；输入 / 输出价格单位为每百万
          token。
        </p>
        {data.entries.length === 0 ? (
          <p className="bg-muted/40 rounded-xl p-8 text-center">
            当前筛选没有符合条件的模型
          </p>
        ) : (
          <Table>
            <TableCaption>原始发布排名与固定锚点支持指数</TableCaption>
            <TableHeader className="[&_tr]:border-0">
              <TableRow className="border-0">
                <TableHead>原排名</TableHead>
                <TableHead>模型</TableHead>
                <TableHead>支持指数</TableHead>
                <TableHead>证据</TableHead>
                <TableHead>稳定性</TableHead>
                <TableHead>输入 / 输出价格</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.entries.map((entry) => (
                <TableRow key={entry.model.slug} className="border-0">
                  <TableCell className="font-mono">{entry.rank}</TableCell>
                  <TableCell>
                    <div className="flex min-w-44 items-center gap-3">
                      <ModelMark model={entry.model} />
                      <div className="space-y-1">
                        <Link
                          className="font-medium hover:underline"
                          href={`/leaderboard/models/${entry.model.slug}`}
                        >
                          {entry.model.name}
                        </Link>
                        <p className="text-muted-foreground text-xs">
                          {entry.model.provider ?? "运营方未知"}
                        </p>
                        {entry.access.weights_url ? (
                          <a
                            className="text-muted-foreground text-xs underline underline-offset-4"
                            href={entry.access.weights_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            开放权重
                          </a>
                        ) : null}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-base">
                    {entry.score.toFixed(1)}
                  </TableCell>
                  <TableCell>
                    <p>
                      {entry.source_count} 项 / {entry.operator_count} 家
                    </p>
                    <p className="text-muted-foreground font-mono text-xs">
                      {Math.round(entry.coverage * 100)}%
                    </p>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {entry.stability?.sensitive
                        ? "对证据变化敏感"
                        : entry.confidence === "HIGH"
                          ? "证据覆盖较高"
                          : entry.confidence === "MEDIUM"
                            ? "证据覆盖有限"
                            : "证据有限"}
                    </Badge>
                    {entry.stability ? (
                      <p className="text-muted-foreground mt-1 text-xs">
                        重算范围 {entry.stability.from_rank}–
                        {entry.stability.to_rank}；不可用{" "}
                        {entry.stability.unavailable} 轮
                      </p>
                    ) : (
                      <p className="text-muted-foreground mt-1 text-xs">
                        未提供稳定性结果
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="min-w-44">
                    <OfficialPrice price={entry.price} compact />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
      {data.pending.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-xl font-medium">综合榜模型的分类证据缺口</h2>
          <p className="text-muted-foreground text-sm">
            这些模型尚未满足当前分类的独立证据资格，不能把未上榜解释为能力较低。
          </p>
          <ul className="flex flex-wrap gap-3">
            {data.pending.map((item) => (
              <li
                key={item.model.slug}
                className="bg-muted/40 rounded-md px-3 py-2 text-sm"
              >
                <Link href={`/leaderboard/models/${item.model.slug}`}>
                  {item.model.name}
                </Link>
                <span className="text-muted-foreground">
                  {" "}
                  · {item.sources} 个来源
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
