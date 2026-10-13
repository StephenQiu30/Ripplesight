import Link from "next/link";
import {
  relativeTime,
  storyPresentation,
  storyObservation,
  homeMonitorHref,
  homeCategories,
} from "./home-format";
import { categories } from "@/components/publication/reading-format";
import { AuthLink } from "@/components/auth/auth-link";
import { Button } from "@/components/ui/button";
import { Content, Heading, InlineCode, Text } from "@/components/ui/content";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
import { HeatHistory } from "@/components/publication/heat-history";
import { ReportSentiment } from "@/components/publication/report-sentiment";
import { StoryTiming } from "@/components/publication/story-timing";

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
        const observation = storyObservation(story, observedAt);
        return (
          <Item
            asChild
            key={story.id}
            className="border-border flex-nowrap items-start gap-6 rounded-none border-x-0 border-t-0 border-b px-0 py-4.5 md:py-6"
          >
            <Content role="listitem" aria-labelledby={`home-story-${story.id}`}>
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
                        homeCategories.find(([key]) => key === category)?.[1] ??
                        categories.find(([key]) => key === category)?.[1] ??
                        category,
                    )
                    .join(" · ") || "事件"}{" "}
                  · 材料标注 {relativeTime(observation.materialAt, observedAt)}
                  {observation.recentMaterials ? " · 24小时内发现材料" : ""}
                  {observation.backfill ? " · 含补录材料" : ""}
                </Text>
                <Heading
                  level={2}
                  appearance="feed"
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
                    <InlineCode>{view.sourceCount}</InlineCode>{" "}
                    {view.sourceCountLabel}
                  </Text>
                  <Text size="xs" tone="muted" className="md:hidden">
                    热度{" "}
                    <InlineCode>
                      {view.heat?.toLocaleString("zh-CN") ?? "—"}
                    </InlineCode>
                  </Text>
                  <ReportSentiment sentiment={story.sentiment} compact />
                </Content>
                {story.timing ? (
                  <StoryTiming timing={story.timing} />
                ) : (
                  <>
                    <Text size="xs" tone="muted">
                      事件参考 {relativeTime(story.first_seen_at, observedAt)} ·
                      最新材料发现{" "}
                      {relativeTime(observation.discoveredAt, observedAt)}
                      {observation.unverifiedDiscovery
                        ? " · 另有材料发现时间待核对"
                        : ""}
                    </Text>
                    <Text size="xs" tone="muted">
                      参考时间不代表已确认发生时间；材料发现不代表新事实。
                    </Text>
                  </>
                )}
                {story.timing ? (
                  <Text size="xs" tone="muted">
                    最新材料发现{" "}
                    {relativeTime(observation.discoveredAt, observedAt)} ·
                    材料发现不代表新事实。
                    {observation.unverifiedDiscovery
                      ? " · 另有材料发现时间待核对"
                      : ""}
                  </Text>
                ) : null}
                {story.attention ? (
                  <Text size="xs" tone="muted">
                    48小时窗口截至{" "}
                    {relativeTime(story.attention.window_end, observedAt)} ·{" "}
                    {story.attention.comparable_participant_count} 个可比来源
                    {story.attention.uncomparable_participant_count > 0
                      ? ` · ${story.attention.uncomparable_participant_count} 个来源不可比`
                      : ""}
                    {!story.attention.complete ? " · 部分来源采集不完整" : ""}
                  </Text>
                ) : null}
                <HeatHistory history={story.history} />
                <Button
                  asChild
                  variant="ghost"
                  size="sm"
                  className="self-start"
                >
                  <AuthLink href={homeMonitorHref(story.title)}>
                    设置监测
                  </AuthLink>
                </Button>
              </ItemContent>
              <Content className="hidden w-30 shrink-0 flex-col items-end gap-2 md:flex">
                <Text size="sm">
                  <InlineCode>
                    {view.heat?.toLocaleString("zh-CN", {
                      maximumFractionDigits: 1,
                    }) ?? "—"}
                  </InlineCode>
                </Text>
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
