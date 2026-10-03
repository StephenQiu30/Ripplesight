import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";
import { AlertDescription, Alert } from "@/components/ui/alert";
import {
  Item,
  ItemContent,
  ItemGroup,
  ItemDescription,
} from "@/components/ui/item";
import { useId } from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { FieldGroup, FieldLabel, Field } from "@/components/ui/field";
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
  const fieldId = useId();

  const href =
    data.board.key === "overall"
      ? "/leaderboard"
      : `/leaderboard/category/${data.board.key}`;
  return (
    <div className="flex flex-col gap-y-10">
      <header className="flex max-w-3xl flex-col gap-y-4">
        <p className="text-muted-foreground text-sm">公开评测共识</p>
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
          {data.board.name}
        </h1>
        <p className="text-muted-foreground leading-7">
          {data.board.description}
        </p>
        <RunStamp run={data.run} />
      </header>
      <NavigationMenu
        viewport={false}
        className="max-w-full justify-start"
        aria-label="模型榜分类"
      >
        <NavigationMenuList className="flex-wrap justify-start gap-2">
          {data.tabs.map((tab) => (
            <NavigationMenuItem key={tab.key}>
              <NavigationMenuLink asChild active={data.board.key === tab.key}>
                <Link
                  href={tab.href}
                  aria-current={data.board.key === tab.key ? "page" : undefined}
                >
                  {tab.name}
                </Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
          ))}
        </NavigationMenuList>
      </NavigationMenu>
      <Item variant="muted" asChild>
        <section
          className="flex flex-col gap-y-3 p-5 sm:p-6"
          aria-label="榜单解读"
        >
          <ItemContent className="min-w-0 gap-3">
            <p className="leading-7">{data.board.how_to_read}</p>
            <ItemDescription className="line-clamp-none leading-6">
              排名由加权 Kemeny
              共识决定，支持指数基于固定锚点。指数不是能力差距或获胜概率；缺失证据不补分、不重新分配预算。
            </ItemDescription>
            <ItemDescription className="line-clamp-none">
              本轮 {data.board.model_count} 个合资格模型，
              {data.board.source_count}
              个来源、{data.board.operator_count} 个运营方。
            </ItemDescription>
            <Link
              className="text-sm underline underline-offset-4"
              href="/leaderboard/rules"
            >
              阅读计算规则
            </Link>
          </ItemContent>
        </section>
      </Item>
      <section className="flex flex-col gap-y-5" aria-label="模型排名">
        <form action={href} method="get">
          <FieldGroup className="flex flex-row flex-wrap items-center gap-4">
            <Field orientation="horizontal" className="w-auto">
              <Checkbox
                name="domestic"
                value="true"
                defaultChecked={domestic}
                id={`${fieldId}-board-reading-field-1`}
              />
              <FieldLabel htmlFor={`${fieldId}-board-reading-field-1`}>
                国内模型
              </FieldLabel>
            </Field>
            <Field orientation="horizontal" className="w-auto">
              <Checkbox
                name="open_weights"
                value="true"
                defaultChecked={openWeights}
                id={`${fieldId}-board-reading-field-2`}
              />
              <FieldLabel htmlFor={`${fieldId}-board-reading-field-2`}>
                开放权重
              </FieldLabel>
            </Field>
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
          </FieldGroup>
        </form>
        <p className="text-muted-foreground text-sm">
          筛选保留原排名，最多展示 30 个模型；输入 / 输出价格单位为每百万
          token。
        </p>
        {data.entries.length === 0 ? (
          <Alert role="note" className="p-8">
            <AlertDescription>当前筛选没有符合条件的模型</AlertDescription>
          </Alert>
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
                      <div className="flex flex-col gap-y-1">
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
        <section className="flex flex-col gap-y-3">
          <h2 className="text-xl font-medium">综合榜模型的分类证据缺口</h2>
          <p className="text-muted-foreground text-sm">
            这些模型尚未满足当前分类的独立证据资格，不能把未上榜解释为能力较低。
          </p>
          <ItemGroup className="flex flex-wrap gap-3">
            {data.pending.map((item) => (
              <Item
                role="listitem"
                variant="muted"
                key={item.model.slug}
                className="px-3 py-2"
              >
                <ItemContent className="min-w-0 gap-3">
                  <Link href={`/leaderboard/models/${item.model.slug}`}>
                    {item.model.name}
                  </Link>
                  <span className="text-muted-foreground">
                    {" "}
                    · {item.sources} 个来源
                  </span>
                </ItemContent>
              </Item>
            ))}
          </ItemGroup>
        </section>
      ) : null}
    </div>
  );
}
