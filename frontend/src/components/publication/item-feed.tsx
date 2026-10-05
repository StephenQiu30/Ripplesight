import Link from "next/link";
import {
  ArrowUpRightIcon,
  BookOpenIcon,
  RssIcon,
  GitBranchIcon,
} from "lucide-react";
import { Fragment } from "react";
import { categories, publicationTime } from "./reading-format";
import { SaveItem } from "@/components/publication/local-reading";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Content, Text, Timestamp } from "@/components/ui/content";
import {
  Item,
  ItemContent,
  ItemGroup,
  ItemTitle,
  ItemDescription,
  ItemActions,
} from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";

export function PublicItemFeed({
  items,
}: {
  items: HotKeyAPI.PublicItemView[];
}) {
  return (
    <ItemGroup className="gap-0">
      {items.map((item) => {
        const icon = item.source.icon_url;
        const safeIcon =
          icon &&
          [
            `/api/site/source-icons/${encodeURIComponent(item.source.key)}.svg`,
            `/api/site/source-icons/${encodeURIComponent(item.source.key)}/avatar-48`,
          ].includes(icon);
        return (
          <Fragment key={item.id}>
            <Item
              asChild
              aria-labelledby={`reading-item-${item.id}`}
              className="items-start gap-3 rounded-none px-4 py-5 sm:px-5"
            >
              <Content as="article" role="listitem" className="flex-nowrap">
                <Avatar size="lg">
                  {safeIcon ? <AvatarImage src={icon} alt="" /> : null}
                  <AvatarFallback>
                    <RssIcon aria-hidden="true" />
                  </AvatarFallback>
                </Avatar>
                <ItemContent className="min-w-0 gap-2">
                  <ItemGroup
                    role="group"
                    aria-label="资讯来源与时间"
                    className="flex-row flex-wrap items-center gap-x-2 gap-y-1"
                  >
                    <ItemTitle className="line-clamp-none break-words">
                      {item.source.name}
                    </ItemTitle>
                    {item.source.first_party ? (
                      <Badge variant="secondary">第一方</Badge>
                    ) : null}
                    <ItemDescription className="line-clamp-none">
                      {item.published_at ? "发布于 " : "发现于 "}
                      <Timestamp dateTime={item.timeline_at}>
                        {publicationTime(item.timeline_at)}
                      </Timestamp>
                    </ItemDescription>
                  </ItemGroup>
                  <Card className="w-full min-w-0 gap-3 overflow-visible rounded-none p-0">
                    <CardHeader className="gap-2 px-0">
                      <CardTitle
                        size="post"
                        role="heading"
                        aria-level={2}
                        id={`reading-item-${item.id}`}
                        className="break-words"
                      >
                        <Link href={item.reading_url}>{item.title}</Link>
                      </CardTitle>
                      <CardDescription
                        size="reading"
                        className="line-clamp-3 break-words"
                      >
                        {item.summary ? (
                          <>
                            {item.summary_origin === "source" ? (
                              <Text as="span">来源摘要： </Text>
                            ) : null}
                            {item.summary}
                          </>
                        ) : item.analysis_state === "not_analyzed" ? (
                          "来源未提供摘要，可前往原文阅读。"
                        ) : (
                          "尚未获取站内内容。"
                        )}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-3 px-0">
                      <ItemGroup
                        role="group"
                        aria-label="资讯标记"
                        className="flex-row flex-wrap gap-2"
                      >
                        {item.category ? (
                          <Badge variant="secondary">
                            {
                              categories.find(
                                ([key]) => key === item.category,
                              )?.[1]
                            }
                          </Badge>
                        ) : null}
                        {item.selected ? (
                          <Badge variant="secondary">精选</Badge>
                        ) : null}
                        {item.backfill ? (
                          <Badge variant="outline">历史导入</Badge>
                        ) : null}
                        {item.analysis_state === "not_analyzed" ? (
                          <Badge variant="outline">未分析</Badge>
                        ) : null}
                        {item.tags.map((tag) => (
                          <Badge
                            key={tag}
                            variant="secondary"
                            className="max-w-full break-all whitespace-normal"
                          >
                            #{tag}
                          </Badge>
                        ))}
                      </ItemGroup>
                      <ItemActions className="flex-wrap justify-between gap-1">
                        <Button asChild variant="ghost" size="feed">
                          <Link href={item.reading_url}>
                            <BookOpenIcon data-icon="inline-start" />
                            站内阅读
                          </Link>
                        </Button>
                        {item.original_url ? (
                          <Button asChild variant="ghost" size="feed">
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
                          <Button asChild variant="ghost" size="feed">
                            <Link href={`/discover/stories/${item.event_id}`}>
                              <GitBranchIcon data-icon="inline-start" />
                              事件脉络
                            </Link>
                          </Button>
                        ) : null}
                        <SaveItem id={item.id} compact />
                      </ItemActions>
                    </CardContent>
                  </Card>
                </ItemContent>
              </Content>
            </Item>
            <Separator />
          </Fragment>
        );
      })}
    </ItemGroup>
  );
}
