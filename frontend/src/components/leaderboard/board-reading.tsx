import Link from "next/link";
import {
  Content,
  Heading,
  Text,
  InlineCode,
  TextLink,
} from "@/components/ui/content";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableCaption,
} from "@/components/ui/table";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageState } from "@/components/system/page-state";
import { BoardPageFrame } from "./page-header";
import { ScoreSupport } from "./reading-parts";

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
      <Content className="reading-columns items-start">
        <Content as="section" aria-label="模型排名" className="min-w-0">
          {data.entries.length ? (
            <Table>
              <TableCaption>
                支持指数为固定锚点 0–100 分；缺失证据不补分。
                <TextLink href="/leaderboard/rules">计算规则</TextLink> ·{" "}
                <TextLink href="/leaderboard/sources">评测来源</TextLink>
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead>#</TableHead>
                  <TableHead>模型</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>支持指数</TableHead>
                  <TableHead>变化</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.entries.map((entry) => (
                  <TableRow key={entry.model.slug}>
                    <TableCell>
                      <InlineCode>
                        {String(entry.rank).padStart(2, "0")}
                      </InlineCode>
                    </TableCell>
                    <TableCell className="py-3">
                      <Content layout="stack" className="min-w-32 gap-0">
                        <Link href={`/leaderboard/models/${entry.model.slug}`}>
                          <Text as="strong" size="sm">
                            {entry.model.name}
                          </Text>
                        </Link>
                        <Text size="xs" tone="muted">
                          {entry.model.provider ?? "运营方未知"}
                        </Text>
                      </Content>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">
                        {entry.access.weights_url ? "开放权重" : "未开放权重"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <ScoreSupport
                        score={entry.score}
                        label={`${entry.model.name}支持指数`}
                      />
                    </TableCell>
                    <TableCell>
                      <Text size="xs" tone="muted" title="暂无上期排名对比">
                        —
                      </Text>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <PageState
              headingLevel={2}
              state="empty"
              title="暂无可展示的已发布模型"
              description="请试试其他维度。"
            />
          )}
        </Content>
        <Content
          as="aside"
          aria-label="榜单动态"
          layout="stack"
          className="gap-10"
        >
          <Card variant="muted">
            <CardHeader>
              <Heading level={2} appearance="sidebar">
                本周变化
              </Heading>
            </CardHeader>
            <CardContent>
              <Text size="sm" tone="muted">
                暂无可比较的历史排名。
              </Text>
              <Text size="xs" tone="muted" className="mt-3">
                {data.board.model_count} 个模型 · {data.board.source_count}{" "}
                个评测来源
              </Text>
            </CardContent>
          </Card>
        </Content>
      </Content>
    </BoardPageFrame>
  );
}
