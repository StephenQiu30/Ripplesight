"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRightIcon, SearchIcon } from "lucide-react";

import { HomeItemFeed, HomeStoryFacts, HomeStoryFeed } from "./home-feed";
import { homeOverview, type HomeReading } from "./home-format";
import { useIdentitySession } from "@/components/auth/session-context";
import {
  categories,
  publicationTime,
  PublicSourceStatus,
} from "@/components/publication/reading-parts";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import {
  Content,
  Heading,
  InlineCode,
  Text,
  Timestamp,
} from "@/components/ui/content";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/empty";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  InputGroup,
  InputGroupInput,
  InputGroupAddon,
  InputGroupButton,
} from "@/components/ui/input-group";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";
import { Separator } from "@/components/ui/separator";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useLayoutScrollContainer } from "@/layout/basic-layout";
import { ReadingLayout } from "@/layout/reading-layout";

export type { HomeReading } from "./home-format";
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

function HomeFailure({
  title,
  description,
  failure,
}: {
  title: string;
  description: string;
  failure?: { code?: string; status?: number };
}) {
  const router = useRouter();
  return (
    <Content layout="stack" className="py-4">
      <Alert variant="destructive" aria-label={title}>
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription>
          <Text>{description}</Text>
          {failure?.code || failure?.status ? (
            <InlineCode className="break-all">
              {[failure.code, failure.status].filter(Boolean).join(" · ")}
            </InlineCode>
          ) : null}
        </AlertDescription>
      </Alert>
      <Button
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => router.refresh()}
      >
        重新加载
      </Button>
    </Content>
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
  const overview = homeOverview(reading);
  const observedAt = reading.observedAt ?? new Date().toISOString();
  return (
    <Content>
      <Content as="header" className="flex flex-col gap-5 px-5 py-6 sm:px-8">
        <Content className="flex flex-wrap items-end justify-between gap-4">
          <Content layout="stack" className="gap-2">
            <Heading level={2}>今日 AI 热点</Heading>
            <Text tone="muted" size="xs">
              {overview.updatedAt ? (
                <>
                  内容更新于{" "}
                  <Timestamp dateTime={overview.updatedAt}>
                    <InlineCode>
                      {publicationTime(overview.updatedAt)}
                    </InlineCode>
                  </Timestamp>
                </>
              ) : (
                "公开内容发布后显示更新时间"
              )}
            </Text>
          </Content>
          <Content className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
            <HomeSearch className="min-w-0 flex-1 sm:w-64" />
            <Button asChild>
              <Link href="/feed/daily.xml">订阅日报</Link>
            </Button>
          </Content>
        </Content>
        <Content as="section" aria-label="当前阅读概览">
          <Separator />
          <Content className="flex flex-wrap items-center gap-x-8 gap-y-3 py-4">
            {overview.itemCount !== null ? (
              <Text size="sm" tone="muted">
                当前资讯 <InlineCode>{overview.itemCount}</InlineCode> 条
              </Text>
            ) : null}
            {overview.storyCount !== null ? (
              <Text size="sm" tone="muted">
                全站热点事件 <InlineCode>{overview.storyCount}</InlineCode> 个
              </Text>
            ) : null}
            {overview.itemCount === null && overview.storyCount === null ? (
              <Text size="sm" tone="muted">
                概览暂时无法读取
              </Text>
            ) : null}
          </Content>
          <Separator />
        </Content>
      </Content>
      <ReadingLayout
        title="公开资讯"
        aside={
          <Content layout="stack" className="gap-8">
            <Content as="section" aria-labelledby="home-stories" layout="stack">
              <Heading level={2} id="home-stories">
                值得关注的事件
              </Heading>
              {reading.unavailable.includes("stories") ? (
                <HomeFailure
                  title="事件暂时无法读取。"
                  description="其他公开内容仍可阅读。"
                  failure={reading.failures?.stories}
                />
              ) : reading.stories.length ? (
                <ItemGroup className="gap-3">
                  {reading.stories.map((story) => (
                    <Item
                      key={story.id}
                      role="listitem"
                      size="sm"
                      className="px-0"
                    >
                      <ItemContent className="min-w-0 gap-2">
                        <ItemTitle className="line-clamp-none break-words">
                          <Link href={`/discover/stories/${story.id}`}>
                            {story.title}
                          </Link>
                        </ItemTitle>
                        <ItemDescription className="break-words">
                          {story.latest_progress ?? story.summary}
                        </ItemDescription>
                        <HomeStoryFacts story={story} />
                      </ItemContent>
                    </Item>
                  ))}
                </ItemGroup>
              ) : (
                <Text tone="muted" size="sm">
                  暂无已发布的公开事件。
                </Text>
              )}
            </Content>
            <Separator />
            <Content as="section" aria-labelledby="home-topics" layout="stack">
              <Heading level={2} id="home-topics">
                探索专题
              </Heading>
              {reading.unavailable.includes("topics") ? (
                <HomeFailure
                  title="专题暂时无法读取。"
                  description="其他公开内容仍可阅读。"
                  failure={reading.failures?.topics}
                />
              ) : reading.topics.length ? (
                <ItemGroup className="gap-3">
                  {reading.topics.slice(0, 4).map((topic) => (
                    <Item
                      key={topic.slug}
                      role="listitem"
                      size="sm"
                      className="px-0"
                    >
                      <ItemContent className="min-w-0">
                        <ItemTitle className="line-clamp-none break-words">
                          <Link href={`/discover/topics/${topic.slug}`}>
                            {topic.name}
                          </Link>
                        </ItemTitle>
                        <ItemDescription className="break-words">
                          {topic.definition}
                        </ItemDescription>
                      </ItemContent>
                    </Item>
                  ))}
                </ItemGroup>
              ) : (
                <Text tone="muted" size="sm">
                  公开专题发布后在这里展示。
                </Text>
              )}
              <Button asChild variant="ghost" size="sm" className="self-start">
                <Link href="/discover/topics">
                  全部专题
                  <ArrowRightIcon data-icon="inline-end" />
                </Link>
              </Button>
            </Content>
            <Separator />
            <Content
              as="section"
              aria-labelledby="home-editions"
              layout="stack"
            >
              <Heading level={2} id="home-editions">
                最新刊物
              </Heading>
              {reading.unavailable.includes("editions") ? (
                <HomeFailure
                  title="刊物暂时无法读取。"
                  description="其他公开内容仍可阅读。"
                  failure={reading.failures?.editions}
                />
              ) : reading.editions.length ? (
                <ItemGroup className="gap-3">
                  {reading.editions.map((edition) => (
                    <Item
                      key={`${edition.kind}-${edition.key}`}
                      role="listitem"
                      size="sm"
                      className="px-0"
                    >
                      <ItemContent className="min-w-0">
                        <ItemTitle className="line-clamp-none break-words">
                          <Link href={edition.reading_url}>
                            {edition.title}
                          </Link>
                        </ItemTitle>
                        <ItemDescription>
                          <Timestamp dateTime={edition.created_at}>
                            <InlineCode>
                              {publicationTime(edition.created_at)}
                            </InlineCode>
                          </Timestamp>
                        </ItemDescription>
                      </ItemContent>
                    </Item>
                  ))}
                </ItemGroup>
              ) : (
                <Text tone="muted" size="sm">
                  最新公开刊物发布后将在这里展示。
                </Text>
              )}
              <Content layout="row">
                <Button asChild variant="ghost" size="sm">
                  <Link href="/editions">
                    全部刊物
                    <ArrowRightIcon data-icon="inline-end" />
                  </Link>
                </Button>
                <Button asChild variant="ghost" size="sm">
                  <Link href="/reports/weekly">阅读公开周报</Link>
                </Button>
              </Content>
            </Content>
            <Card variant="muted">
              <CardHeader>
                <CardTitle>让信息围绕你</CardTitle>
                <CardDescription>
                  关注你在意的话题，回到自己的工作台。
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild size="sm">
                  <Link href={personalHref}>
                    {session ? "管理个人关注" : "登录设置关注"}
                  </Link>
                </Button>
              </CardContent>
            </Card>
          </Content>
        }
      >
        <Content
          as="section"
          aria-label="公开资讯"
          className="min-w-0 px-5 pb-6 sm:px-8"
        >
          {reading.stories.length &&
          !reading.unavailable.includes("stories") ? (
            <Content
              as="section"
              aria-labelledby="home-hot-feed"
              className="pb-8"
            >
              <Heading level={2} id="home-hot-feed">
                全站热点事件
              </Heading>
              <HomeStoryFeed
                stories={reading.stories}
                observedAt={observedAt}
              />
            </Content>
          ) : null}
          <Content className="flex flex-col gap-4 pb-4">
            <Heading level={2}>资讯流</Heading>
            <ToggleGroup
              type="single"
              value={mode}
              size="sm"
              aria-label="首页内容范围"
              onValueChange={(value) => {
                if (value)
                  router.push(
                    homeHref(
                      value === "selected" ? "selected" : "all",
                      category,
                    ),
                  );
              }}
            >
              <ToggleGroupItem value="all">最新发现</ToggleGroupItem>
              <ToggleGroupItem value="selected">精选</ToggleGroupItem>
            </ToggleGroup>
            <Content className="min-w-0 overflow-x-auto py-1">
              <ToggleGroup
                type="single"
                value={category ?? "all"}
                size="sm"
                aria-label="资讯分类"
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
            </Content>
            <Text tone="muted" size="xs">
              最近 7 天 · 发布时间未知时展示发现时间
            </Text>
          </Content>
          <Separator />
          <PublicSourceStatus sources={reading.sourceStatus ?? []} />
          {reading.unavailable.includes("items") ? (
            <HomeFailure
              title="暂时无法读取"
              description="可以重新加载，其他阅读入口仍可使用。"
              failure={reading.failures?.items}
            />
          ) : reading.items.length ? (
            <HomeItemFeed items={reading.items} observedAt={observedAt} />
          ) : (
            <Empty className="py-10">
              <EmptyHeader>
                <EmptyTitle>等待新的公开内容</EmptyTitle>
                <EmptyDescription>
                  {mode === "selected"
                    ? "当前条件下暂无已发布的精选，可以切回最新发现阅读公开帖子。"
                    : "当前条件下还没有已许可发布的帖子，可以切换分类或浏览全部资讯。"}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
          <Content
            role="group"
            aria-label="资讯分页"
            className="flex flex-wrap items-center justify-center gap-2 py-6"
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
          </Content>
        </Content>
      </ReadingLayout>
    </Content>
  );
}
