"use client";

import Link from "next/link";
import { useEffect } from "react";
import {
  ArrowRightIcon,
  BookmarkIcon,
  BookOpenIcon,
  ChartNoAxesColumnIcon,
  CompassIcon,
  HomeIcon,
  SearchIcon,
  RssIcon,
} from "lucide-react";
import { useIdentitySession } from "@/components/auth/session-context";
import {
  categories,
  PublicSourceStatus,
} from "@/components/publication/reading-parts";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Field, FieldLabel } from "@/components/ui/field";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";
import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";
import { Separator } from "@/components/ui/separator";
import { useLayoutScrollContainer } from "@/layout/basic-layout";
import { HomePosts } from "./home-posts";

export type HomeReading = {
  items: HotKeyAPI.PublicItemView[];
  stories: HotKeyAPI.PublicStoryView[];
  topics: HotKeyAPI.PublicTopicSummaryView[];
  editions: HotKeyAPI.PublicEditionIndexView[];
  unavailable: string[];
  sourceStatus?: HotKeyAPI.PublicSourceStatusView[];
  nextCursor?: string | null;
};
type HomeScope = {
  mode?: "all" | "selected";
  category?: HotKeyAPI.PublicItemView["category"];
  cursor?: string;
};
const emptyReading: HomeReading = {
  items: [],
  stories: [],
  topics: [],
  editions: [],
  unavailable: [],
};
const destinations = [
  { href: "/", label: "首页", icon: HomeIcon },
  { href: "/discover?mode=all", label: "全部资讯", icon: RssIcon },
  { href: "/discover/topics", label: "探索专题", icon: CompassIcon },
  { href: "/discover/starred", label: "本机收藏", icon: BookmarkIcon },
  { href: "/reports/weekly", label: "日周月刊", icon: BookOpenIcon },
  { href: "/leaderboard", label: "模型榜", icon: ChartNoAxesColumnIcon },
];
function homeHref(
  mode: "all" | "selected",
  category?: HotKeyAPI.PublicItemView["category"],
  cursor?: string | null,
) {
  const params = new URLSearchParams();
  if (mode === "selected") params.set("mode", mode);
  if (category) params.set("category", category);
  if (cursor) params.set("cursor", cursor);
  return params.size ? `/?${params}` : "/";
}
function ReadingEmpty({
  failed,
  description,
}: {
  failed: boolean;
  description: string;
}) {
  return (
    <Empty className="py-10">
      <EmptyHeader>
        <EmptyTitle>{failed ? "暂时无法读取" : "等待新的公开内容"}</EmptyTitle>
        <EmptyDescription>
          {failed ? "可以重新加载，其他阅读入口仍可使用。" : description}
        </EmptyDescription>
      </EmptyHeader>
      {failed ? (
        <EmptyContent>
          <Button asChild variant="outline" size="sm">
            <Link href="/">重新加载</Link>
          </Button>
        </EmptyContent>
      ) : null}
    </Empty>
  );
}

export function HomeContent({
  reading = emptyReading,
  mode = "all",
  category,
  cursor,
}: { reading?: HomeReading } & HomeScope) {
  const session = useIdentitySession();
  const scroll = useLayoutScrollContainer();
  useEffect(() => {
    scroll?.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [scroll, mode, category, cursor]);
  const personalHref = session ? "/workspace" : "/login?returnTo=%2Fworkspace";
  const discoverParams = new URLSearchParams({ mode, window: "7d" });
  if (category) discoverParams.set("category", category);
  return (
    <div className="flex items-start gap-6 xl:gap-8">
      <aside className="sticky top-4 hidden w-44 shrink-0 lg:block xl:w-48">
        <NavigationMenu
          viewport={false}
          aria-label="首页阅读导航"
          className="w-full max-w-none items-start"
        >
          <NavigationMenuList className="w-full flex-col items-stretch gap-1">
            {destinations.map(({ href, label, icon: Icon }) => (
              <NavigationMenuItem key={href}>
                <NavigationMenuLink
                  asChild
                  active={href === "/"}
                  className="flex-row gap-3 px-3 py-3 text-base"
                >
                  <Link
                    href={href}
                    aria-current={href === "/" ? "page" : undefined}
                  >
                    <Icon className="size-5" aria-hidden="true" />
                    {label}
                  </Link>
                </NavigationMenuLink>
              </NavigationMenuItem>
            ))}
          </NavigationMenuList>
        </NavigationMenu>
        <div className="mt-6 flex flex-col gap-3">
          <Button asChild>
            <Link href={personalHref}>
              {session ? "管理个人关注" : "定制我的关注"}
            </Link>
          </Button>
          <p className="text-muted-foreground px-3 text-xs leading-6">
            配置关键词，让重要的信息持续来到你的工作台。
          </p>
        </div>
      </aside>
      <div className="grid min-w-0 flex-1 grid-cols-1 items-start gap-7 xl:grid-cols-3">
        <div className="min-w-0 xl:col-span-2">
          <section aria-labelledby="home-news">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h1
                id="home-news"
                className="text-2xl font-semibold tracking-tight"
              >
                首页
              </h1>
              <Button asChild variant="ghost" size="sm">
                <Link href="/discover">
                  <SearchIcon data-icon="inline-start" />
                  搜索资讯
                </Link>
              </Button>
            </div>
            <NavigationMenu
              viewport={false}
              aria-label="首页内容范围"
              className="mb-3 w-full max-w-none"
            >
              <NavigationMenuList className="w-full gap-2">
                {(
                  [
                    ["all", "最新发现"],
                    ["selected", "精选"],
                  ] as const
                ).map(([value, label]) => (
                  <NavigationMenuItem key={value} className="flex-1">
                    <Button
                      asChild
                      variant={mode === value ? "secondary" : "ghost"}
                      className="w-full"
                    >
                      <Link
                        href={homeHref(value, category)}
                        aria-current={mode === value ? "page" : undefined}
                      >
                        {label}
                      </Link>
                    </Button>
                  </NavigationMenuItem>
                ))}
              </NavigationMenuList>
            </NavigationMenu>
            <NavigationMenu
              viewport={false}
              aria-label="资讯分类"
              className="mb-3 max-w-full justify-start"
            >
              <NavigationMenuList className="flex-wrap justify-start gap-1">
                <NavigationMenuItem>
                  <Button
                    asChild
                    variant={!category ? "secondary" : "ghost"}
                    size="sm"
                  >
                    <Link
                      href={homeHref(mode)}
                      aria-current={!category ? "page" : undefined}
                    >
                      全部
                    </Link>
                  </Button>
                </NavigationMenuItem>
                {categories.map(([key, label]) => (
                  <NavigationMenuItem key={key}>
                    <Button
                      asChild
                      variant={category === key ? "secondary" : "ghost"}
                      size="sm"
                    >
                      <Link
                        href={homeHref(mode, key)}
                        aria-current={category === key ? "page" : undefined}
                      >
                        {label}
                      </Link>
                    </Button>
                  </NavigationMenuItem>
                ))}
              </NavigationMenuList>
            </NavigationMenu>
            <p className="text-muted-foreground mb-4 text-xs leading-5">
              最近 7 天 · 按内容时间排列，发布时间未知时展示发现时间
            </p>
            <Separator />
            <PublicSourceStatus sources={reading.sourceStatus ?? []} />
            {reading.items.length ? (
              <HomePosts items={reading.items} />
            ) : (
              <ReadingEmpty
                failed={reading.unavailable.includes("items")}
                description={
                  mode === "selected"
                    ? "当前条件下暂无已发布的精选，可以切回最新发现阅读公开帖子。"
                    : "当前条件下还没有已许可发布的帖子，可以切换分类或浏览全部资讯。"
                }
              />
            )}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2 py-4">
              {reading.nextCursor ? (
                <Button asChild variant="outline">
                  <Link href={homeHref(mode, category, reading.nextCursor)}>
                    下一页
                    <ArrowRightIcon data-icon="inline-end" />
                  </Link>
                </Button>
              ) : null}
              {cursor ? (
                <Button asChild variant="ghost">
                  <Link href={homeHref(mode, category)}>回到最新</Link>
                </Button>
              ) : null}
              <Button asChild variant="ghost">
                <Link href={`/discover?${discoverParams}`}>
                  浏览全部资讯
                  <ArrowRightIcon data-icon="inline-end" />
                </Link>
              </Button>
            </div>
          </section>
        </div>
        <aside
          className="flex min-w-0 flex-col gap-7 xl:sticky xl:top-4"
          aria-label="发现更多"
        >
          <form
            action="/discover"
            method="get"
            className="flex items-end gap-2"
          >
            <Input type="hidden" name="mode" value="all" readOnly />
            <Input type="hidden" name="window" value="7d" readOnly />
            <Field className="min-w-0 flex-1">
              <FieldLabel htmlFor="home-search" className="sr-only">
                搜索公开资讯
              </FieldLabel>
              <Input
                id="home-search"
                name="q"
                placeholder="搜索公开资讯"
                maxLength={200}
                required
              />
            </Field>
            <Button
              type="submit"
              variant="secondary"
              size="icon"
              aria-label="搜索公开资讯"
            >
              <SearchIcon />
            </Button>
          </form>
          <section aria-labelledby="home-topics">
            <h2 id="home-topics" className="mb-3 text-lg font-semibold">
              探索专题
            </h2>
            {reading.topics.length ? (
              <ItemGroup className="gap-1">
                {reading.topics.slice(0, 4).map((topic) => (
                  <Item key={topic.slug} role="listitem" className="px-0">
                    <ItemContent>
                      <ItemTitle>
                        <Link href={`/discover/topics/${topic.slug}`}>
                          {topic.name}
                        </Link>
                      </ItemTitle>
                      <ItemDescription className="line-clamp-2 leading-6">
                        {topic.definition}
                      </ItemDescription>
                    </ItemContent>
                  </Item>
                ))}
              </ItemGroup>
            ) : (
              <p className="text-muted-foreground text-sm leading-6">
                {reading.unavailable.includes("topics")
                  ? "专题暂时无法读取。"
                  : "公开专题发布后在这里展示。"}
              </p>
            )}
            <Button asChild variant="ghost" size="sm" className="mt-2">
              <Link href="/discover/topics">
                全部专题
                <ArrowRightIcon data-icon="inline-end" />
              </Link>
            </Button>
          </section>
          <section aria-labelledby="home-stories">
            <h2 id="home-stories" className="mb-3 text-lg font-semibold">
              值得关注的事件
            </h2>
            {reading.stories.length ? (
              <ItemGroup className="gap-1">
                {reading.stories.map((story) => (
                  <Item key={story.id} role="listitem" className="px-0">
                    <ItemContent>
                      <ItemTitle className="line-clamp-none">
                        <Link href={`/discover/stories/${story.id}`}>
                          {story.title}
                        </Link>
                      </ItemTitle>
                      <ItemDescription className="line-clamp-3 leading-6">
                        {story.latest_progress ?? story.summary}
                      </ItemDescription>
                    </ItemContent>
                  </Item>
                ))}
              </ItemGroup>
            ) : (
              <p className="text-muted-foreground text-sm leading-6">
                {reading.unavailable.includes("stories")
                  ? "事件暂时无法读取。"
                  : "暂无已发布的公开事件。"}
              </p>
            )}
          </section>
          <section aria-labelledby="home-weekly">
            <h2 id="home-weekly" className="mb-3 text-lg font-semibold">
              本周阅读
            </h2>
            {reading.editions.length ? (
              <ItemGroup className="gap-1">
                {reading.editions.map((edition) => (
                  <Item key={edition.key} role="listitem" className="px-0">
                    <ItemContent>
                      <ItemTitle className="line-clamp-none">
                        <Link href={edition.reading_url}>{edition.title}</Link>
                      </ItemTitle>
                      <ItemDescription>{edition.key}</ItemDescription>
                    </ItemContent>
                  </Item>
                ))}
              </ItemGroup>
            ) : (
              <p className="text-muted-foreground text-sm leading-6">
                {reading.unavailable.includes("editions")
                  ? "周报暂时无法读取。"
                  : "最新公开周报发布后将在这里展示。"}
              </p>
            )}
            <Button asChild variant="ghost" size="sm" className="mt-2">
              <Link href="/reports/weekly">
                阅读公开周报
                <ArrowRightIcon data-icon="inline-end" />
              </Link>
            </Button>
          </section>
          <Button asChild variant="outline">
            <Link href={personalHref}>
              {session ? "管理个人关注" : "登录设置关注"}
            </Link>
          </Button>
        </aside>
      </div>
    </div>
  );
}
