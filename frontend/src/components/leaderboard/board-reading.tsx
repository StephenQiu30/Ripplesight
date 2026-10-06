import Link from "next/link";

import * as UI from "@/components/ui/content";
import { PageState } from "@/components/system/page-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
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
import { BoardPageFrame } from "./page-header";
import { confidenceLabel } from "./board-format";
import { boardHref } from "./board-navigation";
import { OfficialPrice, ScoreSupport } from "./reading-parts";

export function BoardReading({
  data,
  domestic,
  openWeights,
}: {
  data: HotKeyAPI.BoardView;
  domestic: boolean;
  openWeights: boolean;
}) {
  return (
    <BoardPageFrame
      board={data.board.key}
      domestic={domestic}
      openWeights={openWeights}
      tabs={data.tabs}
      run={data.run}
    >
      <Separator />
      <UI.Content
        as="section"
        aria-label="榜单解读"
        className="flex flex-col gap-3"
      >
        <UI.Heading level={2}>{data.board.name}</UI.Heading>
        <UI.Text tone="muted" size="sm">
          {data.board.description}
        </UI.Text>
        <UI.Text size="sm">{data.board.how_to_read}</UI.Text>
        <UI.Text tone="muted" size="sm">
          本轮 <UI.InlineCode>{data.board.model_count}</UI.InlineCode>{" "}
          个合资格模型，<UI.InlineCode>{data.board.source_count}</UI.InlineCode>{" "}
          个来源、<UI.InlineCode>{data.board.operator_count}</UI.InlineCode>{" "}
          个运营方。
        </UI.Text>
        <UI.Text tone="muted" size="sm">
          排名由加权 Kemeny
          共识决定，支持指数基于固定锚点。指数不是能力差距或获胜概率；缺失证据不补分、不重新分配预算。
        </UI.Text>
      </UI.Content>
      <UI.Content
        as="section"
        aria-label="模型排名"
        className="flex min-w-0 flex-col gap-4"
      >
        <UI.Text tone="muted" size="xs">
          筛选保留原排名，最多展示 30 个模型；输入 / 输出价格单位为每百万
          token。
        </UI.Text>
        {data.entries.length === 0 ? (
          <PageState
            headingLevel={2}
            state="empty"
            eyebrow="暂无结果"
            title={
              domestic || openWeights
                ? "当前筛选没有符合条件的模型"
                : "暂无可展示的已发布模型"
            }
            description="可以清除筛选或查看来源覆盖。没有已发布证据的模型不按零分计入。"
            action={
              <Button asChild variant="secondary">
                <Link href={boardHref(data.board.key)}>查看完整榜单</Link>
              </Button>
            }
          />
        ) : (
          <Table className="min-w-3xl">
            <TableCaption>
              原始发布排名与固定锚点支持指数（0–100）；比例条保持固定尺度
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">原排名</TableHead>
                <TableHead scope="col">模型</TableHead>
                <TableHead scope="col">支持指数</TableHead>
                <TableHead scope="col">证据</TableHead>
                <TableHead scope="col">稳定性</TableHead>
                <TableHead scope="col">输入 / 输出价格</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.entries.map((entry) => (
                <TableRow key={entry.model.slug}>
                  <TableCell>
                    <UI.InlineCode>{entry.rank}</UI.InlineCode>
                  </TableCell>
                  <TableCell>
                    <UI.Content className="flex min-w-40 flex-col gap-1">
                      <UI.TextLink
                        href={`/leaderboard/models/${entry.model.slug}`}
                      >
                        {entry.model.name}
                      </UI.TextLink>
                      <UI.Text tone="muted" size="xs">
                        {entry.model.provider ?? "运营方未知"}
                      </UI.Text>
                      {entry.access.weights_url ? (
                        <UI.TextLink
                          href={entry.access.weights_url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <UI.Text as="span" tone="muted" size="xs">
                            开放权重
                          </UI.Text>
                        </UI.TextLink>
                      ) : null}
                    </UI.Content>
                  </TableCell>
                  <TableCell>
                    <ScoreSupport
                      score={entry.score}
                      label={`${entry.model.name}支持指数`}
                    />
                  </TableCell>
                  <TableCell>
                    <UI.Text size="sm">
                      {entry.source_count} 项 / {entry.operator_count} 家
                    </UI.Text>
                    <UI.Text tone="muted" size="xs">
                      <UI.InlineCode>
                        {Math.round(entry.coverage * 100)}%
                      </UI.InlineCode>
                    </UI.Text>
                  </TableCell>
                  <TableCell>
                    <UI.Content className="flex flex-col gap-1">
                      <Badge variant="secondary">
                        {confidenceLabel(entry)}
                      </Badge>
                      <UI.Text tone="muted" size="xs">
                        {entry.stability
                          ? `重算范围 ${entry.stability.from_rank}–${entry.stability.to_rank}；不可用 ${entry.stability.unavailable} 轮`
                          : "未提供稳定性结果"}
                      </UI.Text>
                    </UI.Content>
                  </TableCell>
                  <TableCell className="min-w-44">
                    <OfficialPrice price={entry.price} compact />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </UI.Content>
      {data.pending.length > 0 ? (
        <UI.Content as="section" className="flex flex-col gap-4">
          <Separator />
          <UI.Heading level={2}>综合榜模型的分类证据缺口</UI.Heading>
          <UI.Text tone="muted" size="sm">
            这些模型尚未满足当前分类的独立证据资格，不能把未上榜解释为能力较低。
          </UI.Text>
          <ItemGroup>
            {data.pending.map((item) => (
              <Item key={item.model.slug} role="listitem">
                <ItemContent className="gap-2">
                  <UI.TextLink href={`/leaderboard/models/${item.model.slug}`}>
                    {item.model.name}
                  </UI.TextLink>
                  <UI.Text tone="muted" size="sm">
                    {item.sources} 个来源
                  </UI.Text>
                </ItemContent>
              </Item>
            ))}
          </ItemGroup>
        </UI.Content>
      ) : null}
    </BoardPageFrame>
  );
}
