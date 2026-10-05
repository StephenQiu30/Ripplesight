"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRightIcon, SearchIcon } from "lucide-react";
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
import { Separator } from "@/components/ui/separator";
import { useLayoutScrollContainer } from "@/layout/basic-layout";
import { ReadingLayout } from "@/layout/reading-layout";
import { PublicItemFeed } from "@/components/publication/item-feed";

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
        <InputGroup className="h-12 rounded-full">
          <InputGroupInput
            ref={input}
            id={id}
            type="search"
            placeholder="搜索资讯、话题或关键词"
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
          <InputGroupAddon align="inline-start">
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
        <PublicItemFeed items={reading.items} />
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
      aside={
        <Card className="min-w-0 p-0">
          <CardHeader className="sticky top-0 hidden px-0 pb-3 lg:grid">
            <CardTitle className="sr-only">发现更多</CardTitle>
            <HomeSearch />
          </CardHeader>
          <CardContent className="flex flex-col gap-4 px-0">
            <Card variant="muted">
              <CardHeader>
                <CardTitle size="section">让信息围绕你</CardTitle>
                <CardDescription>
                  关注你在意的话题，回到自己的工作台。
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild size="lg" className="rounded-full">
                  <Link href={personalHref}>
                    {session ? "管理个人关注" : "登录设置关注"}
                  </Link>
                </Button>
              </CardContent>
            </Card>
            <Card role="region" aria-labelledby="home-topics" variant="muted">
              <CardHeader>
                <CardTitle
                  size="section"
                  id="home-topics"
                  role="heading"
                  aria-level={2}
                >
                  探索专题
                </CardTitle>
              </CardHeader>
              <CardContent>
                {reading.topics.length ? (
                  <ItemGroup className="gap-3">
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
                <Button asChild variant="ghost" size="sm" className="mt-3">
                  <Link href="/discover/topics">
                    全部专题
                    <ArrowRightIcon data-icon="inline-end" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
            <Card role="region" aria-labelledby="home-stories" variant="muted">
              <CardHeader>
                <CardTitle
                  size="section"
                  id="home-stories"
                  role="heading"
                  aria-level={2}
                >
                  值得关注的事件
                </CardTitle>
              </CardHeader>
              <CardContent>
                {reading.stories.length ? (
                  <ItemGroup className="gap-3">
                    {reading.stories.map((story) => (
                      <Item
                        key={story.id}
                        role="listitem"
                        size="sm"
                        className="px-0"
                      >
                        <ItemContent>
                          <ItemTitle className="line-clamp-none break-words">
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
            <Card role="region" aria-labelledby="home-weekly" variant="muted">
              <CardHeader>
                <CardTitle
                  size="section"
                  id="home-weekly"
                  role="heading"
                  aria-level={2}
                >
                  本周阅读
                </CardTitle>
              </CardHeader>
              <CardContent>
                {reading.editions.length ? (
                  <ItemGroup className="gap-3">
                    {reading.editions.map((edition) => (
                      <Item
                        key={edition.key}
                        role="listitem"
                        size="sm"
                        className="px-0"
                      >
                        <ItemContent>
                          <ItemTitle className="line-clamp-none break-words">
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
                <Button asChild variant="ghost" size="sm" className="mt-3">
                  <Link href="/reports/weekly">
                    阅读公开周报
                    <ArrowRightIcon data-icon="inline-end" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          </CardContent>
        </Card>
      }
    >
      <Card
        role="region"
        aria-label="公开资讯"
        className="min-w-0 overflow-visible rounded-none p-0"
      >
        <Tabs
          value={mode}
          activationMode="manual"
          onValueChange={(value) =>
            router.push(
              homeHref(value === "selected" ? "selected" : "all", category),
            )
          }
        >
          <CardHeader className="bg-background/95 sticky top-0 z-10 gap-0 rounded-none px-0 backdrop-blur-sm">
            <CardTitle className="sr-only">资讯流</CardTitle>
            <HomeSearch className="px-4 py-3 lg:hidden" />
            <TabsList
              variant="timeline"
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
              className="hide-scrollbar max-w-full justify-start gap-1 overflow-x-auto px-4 py-3"
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
            <CardDescription className="sr-only">
              最近 7 天 · 发布时间未知时展示发现时间
            </CardDescription>
            <Separator />
          </CardHeader>
          <CardContent className="px-0">
            <TabsContent value="all" className="mt-0">
              {feed}
            </TabsContent>
            <TabsContent value="selected" className="mt-0">
              {feed}
            </TabsContent>
          </CardContent>
        </Tabs>
      </Card>
    </ReadingLayout>
  );
}
