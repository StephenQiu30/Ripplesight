import Link from "next/link";
import { ArrowUpRightIcon, BookOpenIcon } from "lucide-react";
import {
  categories,
  publicationTime,
} from "@/components/publication/reading-parts";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
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
          <Item
            key={item.id}
            asChild
            className="items-start gap-3 px-0 py-5 sm:gap-4 sm:py-6"
          >
            <div role="listitem" aria-labelledby={`home-post-${item.id}`}>
              <Avatar size="lg">
                {safeIcon ? <AvatarImage src={icon} alt="" /> : null}
                <AvatarFallback>
                  {item.source.name.trim().slice(0, 1) || "源"}
                </AvatarFallback>
              </Avatar>
              <ItemContent className="min-w-0 gap-3">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                  <span className="text-foreground text-sm font-medium">
                    {item.source.name}
                  </span>
                  {item.source.first_party ? (
                    <span className="text-muted-foreground">第一方</span>
                  ) : null}
                  <span className="text-muted-foreground" aria-hidden="true">
                    ·
                  </span>
                  <time
                    className="text-muted-foreground"
                    dateTime={item.timeline_at}
                  >
                    {item.published_at ? "发布于 " : "发现于 "}
                    {publicationTime(item.timeline_at)}
                  </time>
                </div>
                <h2
                  id={`home-post-${item.id}`}
                  className="text-lg leading-snug font-semibold tracking-tight break-words sm:text-xl"
                >
                  <Link
                    href={item.reading_url}
                    className="hover:underline focus-visible:underline"
                  >
                    {item.title}
                  </Link>
                </h2>
                {item.summary ? (
                  <p className="text-foreground/85 line-clamp-4 text-base leading-7 break-words">
                    {item.summary_origin === "source" ? (
                      <span className="text-muted-foreground">来源摘要 · </span>
                    ) : null}
                    {item.summary}
                  </p>
                ) : (
                  <p className="text-muted-foreground text-sm leading-6">
                    来源未提供摘要，可阅读原文。
                  </p>
                )}
                <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
                  {item.category ? (
                    <Badge variant="secondary">
                      {categories.find(([key]) => key === item.category)?.[1]}
                    </Badge>
                  ) : null}
                  {item.selected ? (
                    <Badge variant="secondary">精选</Badge>
                  ) : null}
                  {item.backfill ? <span>历史导入</span> : null}
                  {item.analysis_state === "not_analyzed" ? (
                    <span>未分析</span>
                  ) : null}
                  {item.tags.map((tag) => (
                    <span key={tag} className="break-all">
                      #{tag}
                    </span>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  <Button asChild variant="ghost" size="sm">
                    <Link href={item.reading_url}>
                      <BookOpenIcon data-icon="inline-start" />
                      站内阅读
                    </Link>
                  </Button>
                  {item.original_url ? (
                    <Button asChild variant="ghost" size="sm">
                      <a
                        href={item.original_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        来源原文
                        <ArrowUpRightIcon data-icon="inline-end" />
                      </a>
                    </Button>
                  ) : null}
                  {item.event_id ? (
                    <Button asChild variant="ghost" size="sm">
                      <Link href={`/discover/stories/${item.event_id}`}>
                        事件脉络
                      </Link>
                    </Button>
                  ) : null}
                </div>
                {index < items.length - 1 ? (
                  <Separator className="mt-2" />
                ) : null}
              </ItemContent>
            </div>
          </Item>
        );
      })}
    </ItemGroup>
  );
}
