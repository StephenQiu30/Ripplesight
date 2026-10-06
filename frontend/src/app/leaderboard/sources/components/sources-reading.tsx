import * as UI from "@/components/ui/content";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
} from "@/components/ui/item";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import { PageState } from "@/components/system/page-state";
import { RunStamp, SourceStatus } from "@/components/leaderboard/reading-parts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export function SourcesReading({ data }: { data: HotKeyAPI.SourcesView }) {
  return (
    <UI.Content className="flex min-w-0 flex-col gap-8">
      <UI.Content as="header" className="flex flex-col gap-3">
        <UI.Heading level={1}>评测来源与覆盖</UI.Heading>
        <UI.Text tone="muted">
          查看各项证据的运营方、用途与固定预算。注册来源不等于本轮已经采集，交叉参考和系统任务不重复计票。
        </UI.Text>
        <RunStamp run={data.run} />
        <UI.Text tone="muted" size="xs">
          来源说明来自 AIHOT 2026-09-26
          固定注册表；成绩和证据时间以具体发布轮次为准。
        </UI.Text>
      </UI.Content>
      {data.groups.length === 0 ? (
        <PageState
          headingLevel={2}
          state="empty"
          eyebrow="暂无来源"
          title="暂无可展示的评测来源"
          description="当前没有公开来源注册表，可以先查看计算规则。"
          action={
            <Button asChild variant="secondary">
              <UI.TextLink href="/leaderboard/rules">查看计算规则</UI.TextLink>
            </Button>
          }
        />
      ) : (
        data.groups.map((group) => (
          <UI.Content
            as="section"
            key={group.key}
            className="flex flex-col gap-4"
          >
            <Separator />
            <UI.Heading level={2}>{group.name}</UI.Heading>
            <UI.Text tone="muted" size="sm">
              {group.blurb}
            </UI.Text>
            {group.sources.length === 0 ? (
              <Empty>
                <EmptyHeader>
                  <EmptyDescription>该分组暂无已注册来源。</EmptyDescription>
                </EmptyHeader>
              </Empty>
            ) : (
              <ItemGroup>
                {group.sources.map((source) => (
                  <Item key={source.key} asChild>
                    <UI.Content as="article" className="min-w-0">
                      <ItemContent className="min-w-0 gap-3">
                        <UI.Content className="flex flex-wrap items-start justify-between gap-3">
                          <UI.TextLink
                            href={`/leaderboard/sources/${source.key}`}
                          >
                            {source.name}
                          </UI.TextLink>
                          <SourceStatus source={source} />
                        </UI.Content>
                        <ItemDescription className="line-clamp-none">
                          {source.description}
                        </ItemDescription>
                        <UI.Text size="sm">
                          {source.operator} · 预算{" "}
                          <UI.InlineCode>
                            {(source.weight * 100).toFixed(1)}%
                          </UI.InlineCode>
                        </UI.Text>
                        <Badge variant="secondary">
                          {source.collected ? "本轮有证据" : "本轮无证据"}
                        </Badge>
                      </ItemContent>
                    </UI.Content>
                  </Item>
                ))}
              </ItemGroup>
            )}
          </UI.Content>
        ))
      )}
    </UI.Content>
  );
}
