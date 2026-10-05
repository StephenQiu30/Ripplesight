import * as UI from "@/components/ui/content";
import { Item, ItemContent, ItemDescription } from "@/components/ui/item";
import Link from "next/link";

import { RunStamp, SourceStatus } from "@/components/leaderboard/reading-parts";
import { Badge } from "@/components/ui/badge";

export function SourcesReading({ data }: { data: HotKeyAPI.SourcesView }) {
  return (
    <UI.Content className="flex flex-col gap-y-10">
      <UI.Content as="header" className="flex max-w-3xl flex-col gap-y-4">
        <UI.Text className="text-muted-foreground text-sm">模型榜</UI.Text>
        <UI.Heading
          level={1}
          className="text-3xl font-medium tracking-tight sm:text-4xl"
        >
          评测来源与覆盖
        </UI.Heading>
        <UI.Text className="text-muted-foreground leading-7">
          查看各项证据的运营方、用途与固定预算。注册来源不等于本轮已经采集，交叉参考和系统任务不重复计票。
        </UI.Text>
        <RunStamp run={data.run} />
        <UI.Text className="text-muted-foreground text-xs leading-6">
          来源说明来自 AIHOT 2026-09-26
          固定注册表；成绩和证据时间以具体发布轮次为准。
        </UI.Text>
      </UI.Content>
      {data.groups.map((group) => (
        <UI.Content
          as="section"
          key={group.key}
          className="flex flex-col gap-y-5"
        >
          <UI.Content className="flex flex-col gap-y-2">
            <UI.Heading level={2} className="text-xl font-medium">
              {group.name}
            </UI.Heading>
            <UI.Text className="text-muted-foreground text-sm">
              {group.blurb}
            </UI.Text>
          </UI.Content>
          <UI.Content className="grid gap-4 md:grid-cols-2">
            {group.sources.map((source) => (
              <Item variant="muted" key={source.key} asChild>
                <UI.Content as="article" className="flex flex-col gap-y-3 p-5">
                  <ItemContent className="min-w-0 gap-3">
                    <UI.Content className="flex flex-wrap items-start justify-between gap-3">
                      <Link
                        className="font-medium hover:underline"
                        href={`/leaderboard/sources/${source.key}`}
                      >
                        {source.name}
                      </Link>
                      <SourceStatus source={source} />
                    </UI.Content>
                    <ItemDescription className="line-clamp-none leading-6">
                      {source.description}
                    </ItemDescription>
                    <UI.Text className="text-sm">
                      {source.operator} · 预算{" "}
                      <UI.Text as="span" className="font-mono">
                        {(source.weight * 100).toFixed(1)}%
                      </UI.Text>
                    </UI.Text>
                    <Badge variant="secondary">
                      {source.collected ? "本轮有证据" : "本轮无证据"}
                    </Badge>
                  </ItemContent>
                </UI.Content>
              </Item>
            ))}
          </UI.Content>
        </UI.Content>
      ))}
    </UI.Content>
  );
}
