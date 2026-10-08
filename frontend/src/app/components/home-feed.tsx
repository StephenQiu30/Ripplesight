import Link from "next/link";
import { relativeTime, storyPresentation } from "./home-format";
import { categories } from "@/components/publication/reading-format";
import { Content, Heading, InlineCode, Text } from "@/components/ui/content";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
import { ObservationGap } from "@/components/ui/signal";

export function HomeStoryFeed({
  stories,
  observedAt,
}: {
  stories: HotKeyAPI.PublicStoryView[];
  observedAt: string;
}) {
  return (
    <ItemGroup className="gap-0" aria-label="热点事件列表">
      {stories.map((story, index) => {
        const view = storyPresentation(story);
        return (
          <Item
            asChild
            key={story.id}
            className="border-border flex-nowrap items-start gap-6 rounded-none border-x-0 border-t-0 border-b px-0 py-6"
          >
            <Content
              as="article"
              role="listitem"
              aria-labelledby={`home-story-${story.id}`}
            >
              <Text
                as="span"
                tone="muted"
                size="sm"
                className="hidden w-5 shrink-0 md:block"
              >
                <InlineCode>{String(index + 1).padStart(2, "0")}</InlineCode>
              </Text>
              <ItemContent className="min-w-0 gap-2">
                <Text size="xs" tone="muted">
                  {view.categories
                    .map(
                      (category) =>
                        categories.find(([key]) => key === category)?.[1],
                    )
                    .join(" · ") || "事件"}{" "}
                  · {relativeTime(view.time, observedAt)}
                </Text>
                <Heading
                  level={3}
                  id={`home-story-${story.id}`}
                  className="break-words"
                >
                  <Link href={`/discover/stories/${story.id}`}>
                    {story.title}
                  </Link>
                </Heading>
                <Text size="sm" tone="muted" className="hidden md:block">
                  {story.latest_progress ?? story.summary}
                </Text>
                <Content className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <Text size="xs" tone="muted">
                    {view.sources.join(" · ") || "暂无来源"}
                  </Text>
                  <Text size="xs" tone="muted">
                    <InlineCode>{view.sourceCount}</InlineCode> 个来源
                  </Text>
                  <Text size="xs" tone="muted" className="md:hidden">
                    热度{" "}
                    <InlineCode>
                      {view.heat?.toLocaleString("zh-CN") ?? "—"}
                    </InlineCode>
                  </Text>
                  <Text size="xs" tone="muted">
                    情感 暂无数据
                  </Text>
                </Content>
              </ItemContent>
              <Content className="hidden w-30 shrink-0 flex-col items-end gap-2 md:flex">
                <Text size="lead">
                  <InlineCode>
                    {view.heat?.toLocaleString("zh-CN", {
                      maximumFractionDigits: 1,
                    }) ?? "—"}
                  </InlineCode>
                </Text>
                <ObservationGap compact>暂无历史曲线</ObservationGap>
                <Text size="xs" tone="muted">
                  48 小时热度
                </Text>
              </Content>
            </Content>
          </Item>
        );
      })}
    </ItemGroup>
  );
}
