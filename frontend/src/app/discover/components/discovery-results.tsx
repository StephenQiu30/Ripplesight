import { Fragment } from "react";
import Link from "next/link";
import { ArrowUpRightIcon } from "lucide-react";

import * as UI from "@/components/ui/content";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";
import { PageState } from "@/components/system/page-state";
import { SaveItem } from "@/components/publication/local-reading";
import { GroupExpansion } from "@/components/publication/reading-groups";
import {
  categories,
  publicationTime,
} from "@/components/publication/reading-format";

export function DiscoveryResults({
  page,
  timeline,
}: {
  page: HotKeyAPI.PublicItemsPage;
  timeline: HotKeyAPI.PublicTimelinePage | null;
}) {
  if (!page.items.length)
    return (
      <PageState
        headingLevel={2}
        state="empty"
        eyebrow="公开资讯"
        title="没有找到资讯"
        description="试试其他关键词，或放宽分类、时间与来源范围。"
        action={
          <Button asChild variant="outline">
            <Link href="/discover">清除筛选</Link>
          </Button>
        }
      />
    );
  return (
    <ItemGroup className="gap-0">
      {page.items.map((item, index) => {
        const card = timeline?.cards[index];
        return (
          <Fragment key={card?.key ?? item.id}>
            <Separator />
            <Item asChild className="items-start gap-3 px-0 py-5">
              <UI.Content
                as="article"
                role="listitem"
                aria-labelledby={`discover-${item.id}`}
                className="flex-nowrap"
              >
                <ItemContent className="min-w-0 gap-3">
                  <UI.Content layout="row">
                    <Badge variant="secondary">
                      {categories.find(([key]) => key === item.category)?.[1] ??
                        "资讯"}
                    </Badge>
                    {item.selected && <Badge variant="outline">精选</Badge>}
                    {item.backfill && <Badge variant="outline">历史导入</Badge>}
                    {item.analysis_state === "not_analyzed" && (
                      <Badge variant="outline">未分析</Badge>
                    )}
                    {item.source.first_party && (
                      <Badge variant="outline">第一方</Badge>
                    )}
                    <UI.Text tone="muted" size="xs">
                      {item.source.name}
                    </UI.Text>
                    <UI.Text tone="muted" size="xs">
                      {card
                        ? "时间线 "
                        : item.published_at
                          ? "发布于 "
                          : "发现于 "}
                      <UI.InlineCode>
                        <UI.Timestamp
                          dateTime={card?.anchor_at ?? item.timeline_at}
                        >
                          {publicationTime(card?.anchor_at ?? item.timeline_at)}
                        </UI.Timestamp>
                      </UI.InlineCode>
                    </UI.Text>
                  </UI.Content>
                  <ItemTitle className="line-clamp-none break-words">
                    <UI.Heading level={3} id={`discover-${item.id}`}>
                      <UI.TextLink href={item.reading_url}>
                        {item.title}
                      </UI.TextLink>
                    </UI.Heading>
                  </ItemTitle>
                  <ItemDescription className="line-clamp-none break-words">
                    {item.summary ? (
                      <>
                        {item.summary_origin === "source" ? "来源摘要：" : ""}
                        {item.summary}
                      </>
                    ) : item.analysis_state === "not_analyzed" ? (
                      "来源未提供摘要，可前往原文阅读。"
                    ) : (
                      "尚未获取站内内容。"
                    )}
                  </ItemDescription>
                  {card?.group?.latest_development && (
                    <UI.Text size="sm" tone="muted">
                      最新进展 · {card.group.latest_development.title}
                    </UI.Text>
                  )}
                  {card?.group && timeline && (
                    <GroupExpansion
                      group={card.group}
                      filters={timeline.filters}
                    />
                  )}
                  <ItemActions className="flex-wrap">
                    {item.tags.length > 0 && (
                      <UI.Content layout="row">
                        {item.tags.map((tag) => (
                          <Badge
                            key={tag}
                            variant="secondary"
                            className="max-w-full break-all whitespace-normal"
                          >
                            #{tag}
                          </Badge>
                        ))}
                      </UI.Content>
                    )}

                    <Button asChild variant="ghost" size="sm">
                      <Link href={item.reading_url}>站内阅读</Link>
                    </Button>
                    <Button asChild variant="ghost" size="sm">
                      <Link
                        href={item.original_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        来源原文
                        <ArrowUpRightIcon
                          aria-hidden="true"
                          data-icon="inline-end"
                        />
                      </Link>
                    </Button>
                    {item.event_id && (
                      <Button asChild variant="ghost" size="sm">
                        <Link href={`/discover/stories/${item.event_id}`}>
                          事件脉络
                        </Link>
                      </Button>
                    )}
                  </ItemActions>
                </ItemContent>
                <SaveItem id={item.id} compact />
              </UI.Content>
            </Item>
          </Fragment>
        );
      })}
      <Separator />
    </ItemGroup>
  );
}
