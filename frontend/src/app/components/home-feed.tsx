import Link from "next/link";
import { Fragment } from "react";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  ArrowUpRightIcon,
  BookOpenIcon,
  GitBranchIcon,
  MinusIcon,
} from "lucide-react";

import {
  relativeTime,
  storyBadgeLabels,
  storyPresentation,
} from "./home-format";
import {
  categories,
  publicationTime,
} from "@/components/publication/reading-format";
import { SaveItem } from "@/components/publication/local-reading";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Content,
  Heading,
  InlineCode,
  Text,
  Timestamp,
} from "@/components/ui/content";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
} from "@/components/ui/item";
import { cn } from "@/lib/utils";
import { Separator } from "@/components/ui/separator";

export function HomeStoryFacts({
  story,
  showHeat = true,
  heatMobileOnly = false,
}: {
  story: HotKeyAPI.PublicStoryView;
  showHeat?: boolean;
  heatMobileOnly?: boolean;
}) {
  const view = storyPresentation(story);
  const TrendIcon =
    view.trend === "up"
      ? ArrowUpIcon
      : view.trend === "down"
        ? ArrowDownIcon
        : view.trend === "flat"
          ? MinusIcon
          : null;
  return (
    <Content layout="row" className="gap-x-4 gap-y-2">
      {view.sources.length ? (
        <Text as="span" tone="muted" size="xs" className="break-words">
          {view.sources.join(" · ")}
        </Text>
      ) : null}
      {story.attention || view.sources.length ? (
        <Text as="span" tone="muted" size="xs">
          <InlineCode>{view.sourceCount}</InlineCode> {view.sourceCountLabel}
        </Text>
      ) : null}
      {showHeat && view.heat !== null ? (
        <Text
          as="span"
          size="xs"
          className={cn(
            "inline-flex flex-wrap items-center gap-1",
            heatMobileOnly && "md:hidden",
          )}
          aria-label={`热度 ${view.heat}，${view.trendLabel}`}
        >
          热度{" "}
          <InlineCode>
            {view.heat.toLocaleString("zh-CN", { maximumFractionDigits: 1 })}
          </InlineCode>
          {TrendIcon ? (
            <TrendIcon aria-hidden="true" className="size-3" />
          ) : null}
          {view.trendLabel}
        </Text>
      ) : null}
      {story.attention && !story.attention.complete ? (
        <Badge variant="outline">覆盖待补全</Badge>
      ) : null}
    </Content>
  );
}

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
          <Fragment key={story.id}>
            <Item
              asChild
              className="flex-nowrap items-start gap-6 px-0 py-5 md:py-6"
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
                  aria-hidden="true"
                  className="hidden w-5 shrink-0 md:block"
                >
                  <InlineCode>{String(index + 1).padStart(2, "0")}</InlineCode>
                </Text>
                <ItemContent className="min-w-0 gap-2 md:gap-3">
                  <Content layout="row">
                    {view.categories.map((category) => (
                      <Badge key={category} variant="secondary">
                        {categories.find(([key]) => key === category)?.[1]}
                      </Badge>
                    ))}
                    <Text as="span" tone="muted" size="xs">
                      更新于{" "}
                      <Timestamp
                        dateTime={view.time ?? undefined}
                        title={publicationTime(view.time)}
                      >
                        <InlineCode>
                          {relativeTime(view.time, observedAt)}
                        </InlineCode>
                      </Timestamp>
                    </Text>
                    {view.badges.map((badge) => (
                      <Badge key={badge} variant="secondary">
                        {storyBadgeLabels[badge]}
                      </Badge>
                    ))}
                  </Content>
                  <Heading
                    level={3}
                    id={`home-story-${story.id}`}
                    className="break-words"
                  >
                    <Link
                      href={`/discover/stories/${story.id}`}
                      className="block"
                    >
                      {story.title}
                    </Link>
                  </Heading>
                  <ItemDescription className="line-clamp-none hidden break-words md:block">
                    {story.latest_progress ?? story.summary}
                  </ItemDescription>
                  <HomeStoryFacts story={story} heatMobileOnly />
                </ItemContent>
                {view.heat !== null ? (
                  <Content
                    className="hidden w-24 shrink-0 flex-col items-end gap-2 md:flex"
                    aria-label={`热度 ${view.heat}，${view.trendLabel}`}
                  >
                    <Text className="font-medium">
                      <InlineCode>
                        {view.heat.toLocaleString("zh-CN", {
                          maximumFractionDigits: 1,
                        })}
                      </InlineCode>
                    </Text>
                    <Text size="xs" tone="muted">
                      {view.trendLabel}
                    </Text>
                    <Text size="xs" tone="muted" className="hidden md:block">
                      当前热度
                    </Text>
                  </Content>
                ) : null}
              </Content>
            </Item>
            <Separator />
          </Fragment>
        );
      })}
    </ItemGroup>
  );
}

export function HomeItemFeed({
  items,
  observedAt,
}: {
  items: HotKeyAPI.PublicItemView[];
  observedAt: string;
}) {
  return (
    <ItemGroup className="gap-0" aria-label="资讯列表">
      {items.map((item) => (
        <Fragment key={item.id}>
          <Item asChild className="items-start px-0 py-6">
            <Content
              as="article"
              role="listitem"
              aria-labelledby={`home-item-${item.id}`}
            >
              <ItemContent className="min-w-0 gap-3">
                <Content layout="row">
                  {item.category ? (
                    <Badge variant="secondary">
                      {categories.find(([key]) => key === item.category)?.[1]}
                    </Badge>
                  ) : null}
                  <Text as="span" tone="muted" size="xs">
                    {item.published_at ? "发布于 " : "发现于 "}
                    <Timestamp
                      dateTime={item.timeline_at}
                      title={publicationTime(item.timeline_at)}
                    >
                      <InlineCode>
                        {relativeTime(item.timeline_at, observedAt)}
                      </InlineCode>
                    </Timestamp>
                  </Text>
                  {item.selected ? (
                    <Badge variant="secondary">精选</Badge>
                  ) : null}
                  {item.backfill ? (
                    <Badge variant="outline">历史导入</Badge>
                  ) : null}
                  {item.analysis_state === "not_analyzed" ? (
                    <Badge variant="outline">未分析</Badge>
                  ) : null}
                </Content>
                <Heading
                  level={3}
                  id={`home-item-${item.id}`}
                  className="break-words"
                >
                  <Link href={item.reading_url} className="block">
                    {item.title}
                  </Link>
                </Heading>
                <ItemDescription className="line-clamp-none break-words">
                  {item.summary ? (
                    <>
                      {item.summary_origin === "source" ? "来源摘要： " : null}
                      {item.summary}
                    </>
                  ) : item.analysis_state === "not_analyzed" ? (
                    "来源未提供摘要，可前往原文阅读。"
                  ) : (
                    "尚未获取站内内容。"
                  )}
                </ItemDescription>
                <Content layout="row">
                  <Text as="span" tone="muted" size="xs">
                    {item.source.name}
                  </Text>
                  {item.source.first_party ? (
                    <Badge variant="secondary">第一方</Badge>
                  ) : null}
                  {item.tags.map((tag) => (
                    <Badge
                      key={tag}
                      variant="outline"
                      className="max-w-full break-all whitespace-normal"
                    >
                      #{tag}
                    </Badge>
                  ))}
                </Content>
                <ItemActions className="flex-wrap justify-between gap-1">
                  <Button asChild variant="ghost" size="sm">
                    <Link href={item.reading_url}>
                      <BookOpenIcon data-icon="inline-start" />
                      站内阅读
                    </Link>
                  </Button>
                  {item.original_url ? (
                    <Button asChild variant="ghost" size="sm">
                      <Link
                        href={item.original_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        来源原文
                        <ArrowUpRightIcon data-icon="inline-end" />
                      </Link>
                    </Button>
                  ) : null}
                  {item.event_id ? (
                    <Button asChild variant="ghost" size="sm">
                      <Link href={`/discover/stories/${item.event_id}`}>
                        <GitBranchIcon data-icon="inline-start" />
                        事件脉络
                      </Link>
                    </Button>
                  ) : null}
                  <SaveItem id={item.id} compact />
                </ItemActions>
              </ItemContent>
            </Content>
          </Item>
          <Separator />
        </Fragment>
      ))}
    </ItemGroup>
  );
}
