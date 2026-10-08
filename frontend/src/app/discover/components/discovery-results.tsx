import Link from "next/link";
import { Content, Heading, Text } from "@/components/ui/content";
import { Badge } from "@/components/ui/badge";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
import { Button } from "@/components/ui/button";
import { GroupExpansion } from "@/components/publication/reading-groups";
import { PageState } from "@/components/system/page-state";
import { SaveItem } from "@/components/publication/local-reading";
import { publicationTime } from "@/components/publication/reading-format";

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
        title="没有找到资讯"
        description="试试其他关键词，或放宽时间与来源范围。"
        action={
          <Button asChild variant="outline">
            <Link href="/discover">清除筛选</Link>
          </Button>
        }
      />
    );
  return (
    <ItemGroup className="gap-0">
      {page.items.map((item, index) => (
        <Item
          key={item.id}
          asChild
          className="border-border flex-nowrap items-start gap-4 rounded-none border-x-0 border-t-0 border-b px-0 py-5"
        >
          <Content role="listitem" aria-labelledby={`discover-${item.id}`}>
            <ItemContent className="min-w-0 gap-3">
              <Content layout="row">
                <Badge variant="secondary">资讯</Badge>
                <Text size="xs" tone="muted">
                  {item.source.name} · {publicationTime(item.timeline_at)}
                </Text>
              </Content>
              <Heading level={2} appearance="result" id={`discover-${item.id}`}>
                <Link href={item.reading_url}>{item.title}</Link>
              </Heading>
              <Text size="sm" tone="muted">
                {item.summary || "暂无摘要，可打开原文阅读。"}
              </Text>
              {timeline?.cards[index]?.group?.latest_development ? (
                <Text size="xs" tone="muted">
                  最新进展 ·{" "}
                  {timeline.cards[index].group!.latest_development!.title}
                </Text>
              ) : null}
              {timeline?.cards[index]?.group ? (
                <GroupExpansion
                  group={timeline.cards[index].group!}
                  filters={timeline.filters}
                />
              ) : null}
              {item.event_id ? (
                <Link href={`/discover/stories/${item.event_id}`}>
                  <Text size="xs" tone="muted">
                    查看关联事件 →
                  </Text>
                </Link>
              ) : null}
            </ItemContent>
            <SaveItem id={item.id} compact />
          </Content>
        </Item>
      ))}
    </ItemGroup>
  );
}
