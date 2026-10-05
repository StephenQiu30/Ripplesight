import Link from "next/link";
import { ArrowUpRightIcon, BookOpenIcon } from "lucide-react";
import { Fragment } from "react";
import {
  categories,
  publicationTime,
} from "@/components/publication/reading-parts";
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
import {
  Item,
  ItemContent,
  ItemGroup,
  ItemTitle,
  ItemDescription,
  ItemActions,
} from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";

export function HomePosts({ items }: { items: HotKeyAPI.PublicItemView[] }) {
  return (
    <ItemGroup className="gap-0">
      {items.map((item, index) => {
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
              role="listitem"
              aria-labelledby={`home-post-${item.id}`}
              className="flex-col items-stretch gap-3 px-0 py-4"
            >
              <ItemGroup
                role="group"
                aria-label="资讯来源与时间"
                className="flex-row items-center gap-3"
              >
                <Avatar size="lg">
                  {safeIcon ? <AvatarImage src={icon} alt="" /> : null}
                  <AvatarFallback>
                    {item.source.name.trim().slice(0, 1) || "源"}
                  </AvatarFallback>
                </Avatar>
                <ItemContent className="min-w-0 flex-row flex-wrap items-center gap-2">
                  <ItemTitle className="line-clamp-none break-words">
                    {item.source.name}
                  </ItemTitle>
                  {item.source.first_party ? (
                    <Badge variant="outline">第一方</Badge>
                  ) : null}
                  <ItemDescription>
                    {item.published_at ? "发布于 " : "发现于 "}
                    {publicationTime(item.timeline_at)}
                  </ItemDescription>
                </ItemContent>
              </ItemGroup>
              <Card className="w-full min-w-0 gap-3 p-0">
                <CardHeader className="gap-2 px-0">
                  <CardTitle
                    role="heading"
                    aria-level={2}
                    id={`home-post-${item.id}`}
                    className="break-words"
                  >
                    <Link href={item.reading_url}>{item.title}</Link>
                  </CardTitle>
                  <CardDescription className="line-clamp-4 break-words">
                    {item.summary
                      ? `${item.summary_origin === "source" ? "来源摘要 · " : ""}${item.summary}`
                      : "尚未获取站内内容。"}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-2 px-0">
                  <ItemGroup
                    role="group"
                    aria-label="资讯标记"
                    className="flex-row flex-wrap gap-2"
                  >
                    {item.category ? (
                      <Badge variant="secondary">
                        {categories.find(([key]) => key === item.category)?.[1]}
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
                  <ItemActions className="flex-wrap gap-1">
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
                          事件脉络
                        </Link>
                      </Button>
                    ) : null}
                  </ItemActions>
                </CardContent>
              </Card>
            </Item>
            {index < items.length - 1 ? <Separator /> : null}
          </Fragment>
        );
      })}
    </ItemGroup>
  );
}
