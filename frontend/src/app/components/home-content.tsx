"use client";

import Link from "next/link";
import { ArrowUpRightIcon } from "lucide-react";

import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
} from "@/components/ui/navigation-menu";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
} from "@/components/ui/empty";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
} from "@/components/ui/item";
import {
  categories,
  PublicItemCards,
} from "@/components/publication/reading-parts";
import { useIdentitySession } from "@/components/auth/session-context";
import { HeroSection } from "./hero-section";

export type HomeReading = {
  items: HotKeyAPI.PublicItemView[];
  stories: HotKeyAPI.PublicStoryView[];
  topics: HotKeyAPI.PublicTopicSummaryView[];
  editions: HotKeyAPI.PublicEditionIndexView[];
  unavailable: string[];
};

const emptyReading: HomeReading = {
  items: [],
  stories: [],
  topics: [],
  editions: [],
  unavailable: [],
};

function ReadingEmpty({
  failed,
  description,
}: {
  failed: boolean;
  description: string;
}) {
  return (
    <Empty>
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
}: {
  reading?: HomeReading;
}) {
  const session = useIdentitySession();
  return (
    <div className="flex flex-col gap-10 sm:gap-12">
      <HeroSection />
      <div className="grid items-start gap-12 lg:grid-cols-3">
        <section aria-labelledby="home-news" className="min-w-0 lg:col-span-2">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-muted-foreground mb-2 text-xs">
                NEWS & INSIGHTS
              </p>
              <h2
                id="home-news"
                className="text-2xl font-medium tracking-tight"
              >
                最新资讯
              </h2>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link href="/discover">
                全部资讯
                <ArrowUpRightIcon data-icon="inline-end" />
              </Link>
            </Button>
          </div>
          <NavigationMenu
            viewport={false}
            aria-label="资讯分类"
            className="mb-5 max-w-full justify-start"
          >
            <NavigationMenuList className="flex-wrap justify-start gap-2">
              {categories.map(([key, label]) => (
                <NavigationMenuItem key={key}>
                  <Button asChild variant="secondary" size="sm">
                    <Link href={`/discover?mode=all&category=${key}`}>
                      {label}
                    </Link>
                  </Button>
                </NavigationMenuItem>
              ))}
            </NavigationMenuList>
          </NavigationMenu>
          {reading.items.length ? (
            <PublicItemCards items={reading.items} />
          ) : (
            <ReadingEmpty
              failed={reading.unavailable.includes("items")}
              description="已许可发布的资讯会在这里展示，现阶段可以先探索分类与阅读入口。"
            />
          )}
        </section>
        <aside className="flex min-w-0 flex-col gap-10">
          <section aria-labelledby="home-stories">
            <div className="mb-4">
              <p className="text-muted-foreground mb-2 text-xs">
                FOLLOW THE STORY
              </p>
              <h2 id="home-stories" className="text-xl font-medium">
                值得关注的事件
              </h2>
            </div>
            {reading.stories.length ? (
              <ItemGroup>
                {reading.stories.map((story) => (
                  <Item key={story.id} role="listitem">
                    <Link
                      href={`/discover/stories/${story.id}`}
                      className="flex w-full min-w-0 items-start justify-between gap-4"
                    >
                      <ItemContent>
                        <ItemTitle className="line-clamp-none">
                          {story.title}
                        </ItemTitle>
                        <ItemDescription className="line-clamp-3">
                          {story.latest_progress ?? story.summary}
                        </ItemDescription>
                      </ItemContent>
                      <ArrowUpRightIcon aria-hidden="true" />
                    </Link>
                  </Item>
                ))}
              </ItemGroup>
            ) : (
              <ReadingEmpty
                failed={reading.unavailable.includes("stories")}
                description="公开事件发布后，可以沿着报道与进展了解来龙去脉。"
              />
            )}
          </section>
          <section aria-labelledby="home-weekly">
            <h2 id="home-weekly" className="text-xl font-medium">
              每周，读懂重要变化
            </h2>
            <p className="text-muted-foreground mt-3 text-sm leading-6">
              公开周报汇集已发布的资讯。登录后可配置个人关键词，并查看已生成的报告。
            </p>
            {reading.editions.length ? (
              <ItemGroup className="mt-4">
                {reading.editions.map((edition) => (
                  <Item key={edition.key} role="listitem">
                    <Link
                      href={edition.reading_url}
                      className="flex w-full min-w-0 items-start justify-between gap-4"
                    >
                      <ItemContent>
                        <ItemTitle className="line-clamp-none">
                          {edition.title}
                        </ItemTitle>
                        <ItemDescription>{edition.key}</ItemDescription>
                      </ItemContent>
                    </Link>
                  </Item>
                ))}
              </ItemGroup>
            ) : (
              <p className="text-muted-foreground mt-4 text-xs">
                {reading.unavailable.includes("editions")
                  ? "周报暂时无法读取。"
                  : "最新公开周报发布后将在这里展示。"}
              </p>
            )}
            <div className="mt-5 flex flex-wrap gap-2">
              <Button asChild variant="outline" size="sm">
                <Link href="/reports/weekly">阅读公开周报</Link>
              </Button>
              <Button asChild variant="ghost" size="sm">
                <Link
                  href={session ? "/workspace" : "/login?returnTo=%2Fworkspace"}
                >
                  {session ? "管理个人关注" : "登录设置关注"}
                </Link>
              </Button>
            </div>
          </section>
        </aside>
      </div>
      <section aria-labelledby="home-explore">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <h2 id="home-explore" className="text-2xl font-medium tracking-tight">
            继续探索
          </h2>
          <Button asChild variant="ghost" size="sm">
            <Link href="/discover/topics">
              全部专题
              <ArrowUpRightIcon data-icon="inline-end" />
            </Link>
          </Button>
        </div>
        <ItemGroup className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {(reading.topics.length
            ? reading.topics.slice(0, 2).map((topic) => ({
                href: `/discover/topics/${topic.slug}`,
                title: topic.name,
                description: topic.definition,
              }))
            : [
                {
                  href: "/discover/topics",
                  title: "行业专题",
                  description:
                    "按公司、领域与内容类型探索资讯，把零散报道放回上下文。",
                },
                {
                  href: "/reports/daily",
                  title: "日周月刊",
                  description:
                    "按刊期阅读公开资讯，回顾每天、每周与每月的重要变化。",
                },
              ]
          )
            .concat([
              {
                href: "/leaderboard",
                title: "模型榜",
                description: "查看已发布的模型评测、证据覆盖与计算规则。",
              },
            ])
            .map((entry) => (
              <Item key={entry.href} role="listitem" variant="muted">
                <Link
                  href={entry.href}
                  className="flex w-full min-w-0 items-start justify-between gap-4"
                >
                  <ItemContent>
                    <ItemTitle>{entry.title}</ItemTitle>
                    <ItemDescription>{entry.description}</ItemDescription>
                  </ItemContent>
                  <ArrowUpRightIcon aria-hidden="true" />
                </Link>
              </Item>
            ))}
        </ItemGroup>
      </section>
    </div>
  );
}
