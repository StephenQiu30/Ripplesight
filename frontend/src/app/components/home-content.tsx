"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
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
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  InputGroup,
  InputGroupInput,
  InputGroupAddon,
  InputGroupButton,
} from "@/components/ui/input-group";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
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
import { ReadingLayout } from "@/layout/reading-layout";
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

function HomeSearch({ className }: { className?: string }) {
  const router = useRouter();
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const search = () => {
    if (!query.trim()) {
      input.current?.focus();
      return;
    }
    const params = new URLSearchParams({
      mode: "all",
      window: "7d",
      q: query.trim(),
    });
    router.push(`/discover?${params}`);
  };
  return (
    <FieldGroup role="search" aria-label="公开资讯检索" className={className}>
      <Field>
        <FieldLabel htmlFor={id} className="sr-only">
          搜索公开资讯
        </FieldLabel>
        <InputGroup>
          <InputGroupInput
            ref={input}
            id={id}
            type="search"
            placeholder="搜索公开资讯"
            maxLength={200}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                event.preventDefault();
                search();
              }
            }}
          />
          <InputGroupAddon align="inline-end">
            <InputGroupButton
              size="icon-xs"
              aria-label="搜索公开资讯"
              onClick={search}
            >
              <SearchIcon />
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
      </Field>
    </FieldGroup>
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
  const router = useRouter();
  useEffect(() => {
    scroll?.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [scroll, mode, category, cursor]);
  const personalHref = session ? "/workspace" : "/login?returnTo=%2Fworkspace";
  const discoverParams = new URLSearchParams({ mode, window: "7d" });
  if (category) discoverParams.set("category", category);
  const feed = (
    <>
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
      <ItemGroup
        role="group"
        aria-label="资讯分页"
        className="mt-4 flex-row flex-wrap items-center justify-center gap-2 py-4"
      >
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
      </ItemGroup>
    </>
  );
  return (
    <ReadingLayout
      title="公开资讯"
      navigation={
        <Card className="min-w-0 p-0">
          <CardHeader className="sr-only">
            <CardTitle>阅读导航</CardTitle>
          </CardHeader>
          <CardContent className="flex max-w-48 flex-col gap-5 px-0">
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
                      className="flex-row gap-3 px-3 py-3"
                    >
                      <Link
                        href={href}
                        aria-current={href === "/" ? "page" : undefined}
                      >
                        <Icon aria-hidden="true" />
                        {label}
                      </Link>
                    </NavigationMenuLink>
                  </NavigationMenuItem>
                ))}
              </NavigationMenuList>
            </NavigationMenu>
            <Button asChild>
              <Link href={personalHref}>
                {session ? "管理个人关注" : "定制我的关注"}
              </Link>
            </Button>
            <CardDescription>
              配置关键词，让重要的信息持续来到你的工作台。
            </CardDescription>
          </CardContent>
        </Card>
      }
      aside={
        <Card className="min-w-0 p-0">
          <CardHeader className="hidden px-0 lg:grid">
            <CardTitle className="sr-only">发现更多</CardTitle>
            <HomeSearch />
          </CardHeader>
          <CardContent className="flex flex-col gap-6 px-0">
            <Card
              role="region"
              aria-labelledby="home-topics"
              size="sm"
              className="p-0"
            >
              <CardHeader className="px-0">
                <CardTitle id="home-topics" role="heading" aria-level={2}>
                  探索专题
                </CardTitle>
              </CardHeader>
              <CardContent className="px-0">
                {reading.topics.length ? (
                  <ItemGroup className="gap-1">
                    {reading.topics.slice(0, 4).map((topic) => (
                      <Item
                        key={topic.slug}
                        role="listitem"
                        size="sm"
                        className="px-0"
                      >
                        <ItemContent>
                          <ItemTitle>
                            <Link href={`/discover/topics/${topic.slug}`}>
                              {topic.name}
                            </Link>
                          </ItemTitle>
                          <ItemDescription>{topic.definition}</ItemDescription>
                        </ItemContent>
                      </Item>
                    ))}
                  </ItemGroup>
                ) : (
                  <CardDescription>
                    {reading.unavailable.includes("topics")
                      ? "专题暂时无法读取。"
                      : "公开专题发布后在这里展示。"}
                  </CardDescription>
                )}
                <Button asChild variant="ghost" size="sm" className="mt-2">
                  <Link href="/discover/topics">
                    全部专题
                    <ArrowRightIcon data-icon="inline-end" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
            <Card
              role="region"
              aria-labelledby="home-stories"
              size="sm"
              className="p-0"
            >
              <CardHeader className="px-0">
                <CardTitle id="home-stories" role="heading" aria-level={2}>
                  值得关注的事件
                </CardTitle>
              </CardHeader>
              <CardContent className="px-0">
                {reading.stories.length ? (
                  <ItemGroup className="gap-1">
                    {reading.stories.map((story) => (
                      <Item
                        key={story.id}
                        role="listitem"
                        size="sm"
                        className="px-0"
                      >
                        <ItemContent>
                          <ItemTitle className="line-clamp-none">
                            <Link href={`/discover/stories/${story.id}`}>
                              {story.title}
                            </Link>
                          </ItemTitle>
                          <ItemDescription>
                            {story.latest_progress ?? story.summary}
                          </ItemDescription>
                        </ItemContent>
                      </Item>
                    ))}
                  </ItemGroup>
                ) : (
                  <CardDescription>
                    {reading.unavailable.includes("stories")
                      ? "事件暂时无法读取。"
                      : "暂无已发布的公开事件。"}
                  </CardDescription>
                )}
              </CardContent>
            </Card>
            <Card
              role="region"
              aria-labelledby="home-weekly"
              size="sm"
              className="p-0"
            >
              <CardHeader className="px-0">
                <CardTitle id="home-weekly" role="heading" aria-level={2}>
                  本周阅读
                </CardTitle>
              </CardHeader>
              <CardContent className="px-0">
                {reading.editions.length ? (
                  <ItemGroup className="gap-1">
                    {reading.editions.map((edition) => (
                      <Item
                        key={edition.key}
                        role="listitem"
                        size="sm"
                        className="px-0"
                      >
                        <ItemContent>
                          <ItemTitle className="line-clamp-none">
                            <Link href={edition.reading_url}>
                              {edition.title}
                            </Link>
                          </ItemTitle>
                          <ItemDescription>{edition.key}</ItemDescription>
                        </ItemContent>
                      </Item>
                    ))}
                  </ItemGroup>
                ) : (
                  <CardDescription>
                    {reading.unavailable.includes("editions")
                      ? "周报暂时无法读取。"
                      : "最新公开周报发布后将在这里展示。"}
                  </CardDescription>
                )}
                <Button asChild variant="ghost" size="sm" className="mt-2">
                  <Link href="/reports/weekly">
                    阅读公开周报
                    <ArrowRightIcon data-icon="inline-end" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
            <Button asChild variant="outline">
              <Link href={personalHref}>
                {session ? "管理个人关注" : "登录设置关注"}
              </Link>
            </Button>
          </CardContent>
        </Card>
      }
    >
      <Card role="region" aria-label="公开资讯" className="min-w-0 p-0">
        <Tabs
          value={mode}
          activationMode="manual"
          onValueChange={(value) =>
            router.push(
              homeHref(value === "selected" ? "selected" : "all", category),
            )
          }
        >
          <CardHeader className="gap-3 px-0">
            <CardTitle className="sr-only">资讯流</CardTitle>
            <HomeSearch className="lg:hidden" />
            <TabsList
              variant="line"
              aria-label="首页内容范围"
              className="w-full"
            >
              <TabsTrigger value="all">最新发现</TabsTrigger>
              <TabsTrigger value="selected">精选</TabsTrigger>
            </TabsList>
            <ToggleGroup
              type="single"
              value={category ?? "all"}
              size="sm"
              aria-label="资讯分类"
              className="max-w-full flex-wrap justify-start"
              onValueChange={(value) => {
                if (value)
                  router.push(
                    homeHref(
                      mode,
                      value === "all"
                        ? undefined
                        : categories.find(([key]) => key === value)?.[0],
                    ),
                  );
              }}
            >
              <ToggleGroupItem value="all">全部</ToggleGroupItem>
              {categories.map(([key, label]) => (
                <ToggleGroupItem key={key} value={key}>
                  {label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            <CardDescription>
              最近 7 天 · 发布时间未知时展示发现时间
            </CardDescription>
          </CardHeader>
          <Separator />
          <CardContent className="px-0">
            <TabsContent value="all">{feed}</TabsContent>
            <TabsContent value="selected">{feed}</TabsContent>
          </CardContent>
        </Tabs>
      </Card>
    </ReadingLayout>
  );
}
