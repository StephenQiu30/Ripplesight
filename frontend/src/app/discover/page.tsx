import { PageHeader } from "@/components/system/page-header";
import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { Suspense } from "react";
import {
  getPublicTopicDirectory,
  listPublicItems,
  getPublicReadingTimeline,
} from "@/api/gongkaifabu";
import * as UI from "@/components/ui/content";
import { Button } from "@/components/ui/button";
import { PageState } from "@/components/system/page-state";
import {
  categories,
  PublicSourceStatus,
  PublicationFailure,
} from "@/components/publication/reading-parts";
import { publicSiteMetadata } from "@/components/publication/site-metadata";
import { DiscoveryFilters } from "./components/discovery-filters";
import { DiscoveryResults } from "./components/discovery-results";
import { DiscoveryPlatforms } from "./components/discovery-platforms";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { DiscoveryTopics } from "./components/discovery-topics";
import {
  discoveryScope,
  discoveryFailure,
  discoverySources,
  discoveryHref,
  type DiscoveryParams,
} from "./components/discovery-data";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}): Promise<Metadata> {
  const params = await searchParams;
  let indexable = false;
  if (!Object.values(params).some(Boolean)) {
    try {
      const page = await listPublicItems({
        mode: "all",
        window: "24h",
        limit: 20,
      });
      indexable =
        page.items.length > 0 &&
        page.items.every((item) => item.indexable === true);
    } catch {
      // Failed or empty reading pages are not indexed.
    }
  }
  return publicSiteMetadata({
    title: "探索",
    path: "/discover",
    imagePath: "/og/pages/hot.png",
    indexable,
  });
}

export default async function DiscoverPage({
  searchParams,
}: {
  searchParams: Promise<DiscoveryParams>;
}) {
  await connection();
  const params = await searchParams;
  return (
    <Suspense
      fallback={
        <>
          <UI.Heading level={1} className="sr-only">
            正在检索公开资讯
          </UI.Heading>
          <PageState
            state="loading"
            eyebrow="探索"
            title="正在检索公开资讯"
            description="正在读取结果与专题目录。"
          />
        </>
      }
    >
      <DiscoveryReadingPage params={params} />
    </Suspense>
  );
}

async function DiscoveryReadingPage({ params }: { params: DiscoveryParams }) {
  const scope = discoveryScope(params);
  const timelineMode =
    scope.mode === "selected" && scope.by === "timeline" && !params.q;
  const filters = {
    window: scope.window,
    category: scope.category,
    source_key: params.source_key || undefined,
    tag: params.tag || undefined,
    topic: params.topic || undefined,
    cursor: params.cursor || undefined,
  };
  const [reading, topics, sourceDirectory] = await Promise.allSettled([
    timelineMode
      ? getPublicReadingTimeline({
          ...filters,
          channel: scope.channel ?? "all",
          limit: 20,
        })
      : listPublicItems({
          ...scope,
          ...filters,
          q: params.q || undefined,
          search_order: params.search_order === "time" ? "time" : "relevance",
          limit: params.q ? 40 : 30,
        }),
    getPublicTopicDirectory(),
    timelineMode
      ? listPublicItems({ mode: "all", window: "24h", limit: 1 })
      : Promise.resolve(null),
  ]);
  const timeline =
    reading.status === "fulfilled" && "cards" in reading.value
      ? reading.value
      : null;
  const page: HotKeyAPI.PublicItemsPage | null =
    reading.status === "fulfilled"
      ? "cards" in reading.value
        ? {
            items: reading.value.cards.map((card) => card.item),
            next_cursor: reading.value.next_cursor,
            snapshot_at: reading.value.snapshot_at,
            source_status:
              sourceDirectory.status === "fulfilled"
                ? sourceDirectory.value?.source_status
                : undefined,
          }
        : reading.value
      : null;
  const contentType = ["events", "items", "comments"].includes(
    params.type ?? "",
  )
    ? params.type
    : "all";
  const currentHref = discoveryHref(params, params.cursor);
  return (
    <UI.Content layout="stack" className="gap-6">
      <PageHeader
        title={<>探索</>}
        description={
          <>检索事件与资讯，沿着来源阅读原文。评论与情感数据发布后开放检索。</>
        }
      />
      <DiscoveryFilters
        key={JSON.stringify(params)}
        {...scope}
        params={params}
        resultCount={
          page && (contentType === "all" || contentType === "items")
            ? page.items.length
            : undefined
        }
        categories={categories}
        sources={discoverySources(page)}
      />
      <UI.Content className="reading-columns">
        <UI.Content
          as="section"
          aria-label="搜索结果"
          layout="stack"
          className="min-w-0"
        >
          {page ? (
            <>
              <PublicSourceStatus sources={page.source_status ?? []} compact />
              {contentType === "comments" || contentType === "events" ? (
                <PageState
                  headingLevel={2}
                  state="empty"
                  title={
                    contentType === "events"
                      ? "事件检索尚未开放"
                      : "暂无公开评论"
                  }
                  description={
                    contentType === "events"
                      ? "可在事件页阅读当前热榜；全量事件搜索尚未接入。"
                      : "公开评论发布后将在这里提供检索。"
                  }
                />
              ) : (
                <DiscoveryResults page={page} timeline={timeline} />
              )}
              {(contentType === "all" || contentType === "items") &&
                (params.cursor || page.next_cursor) && (
                  <UI.Content
                    role="navigation"
                    aria-label="结果分页"
                    className="flex flex-wrap items-center justify-between gap-3"
                  >
                    {params.cursor ? (
                      <Button asChild variant="outline" size="navigation">
                        <Link href={discoveryHref(params)}>回到第一页</Link>
                      </Button>
                    ) : null}
                    {page.next_cursor ? (
                      <Button
                        asChild
                        variant="outline"
                        size="navigation"
                        className="ml-auto"
                      >
                        <Link href={discoveryHref(params, page.next_cursor)}>
                          下一页
                        </Link>
                      </Button>
                    ) : null}
                  </UI.Content>
                )}
            </>
          ) : (
            <PublicationFailure
              headingLevel={2}
              error={discoveryFailure(
                reading.status === "rejected" ? reading.reason : undefined,
              )}
              href={currentHref}
            />
          )}
        </UI.Content>
        <UI.Content
          as="aside"
          aria-label="搜索筛选与主题"
          layout="stack"
          className="gap-10"
        >
          <DiscoveryPlatforms
            failed={!page || sourceDirectory.status === "rejected"}
            sources={discoverySources(page)}
            params={params}
          />
          <DiscoveryTopics
            directory={topics.status === "fulfilled" ? topics.value : null}
            error={topics.status === "rejected" ? topics.reason : undefined}
            retryHref={currentHref}
          />
          <UI.Content as="section" layout="stack">
            <UI.Heading level={2} appearance="sidebar">
              相关搜索
            </UI.Heading>
            <UI.Text size="sm" tone="muted">
              暂无搜索建议。
            </UI.Text>
          </UI.Content>
          <Card variant="muted">
            <CardHeader>
              <UI.Heading level={2} appearance="sidebar">
                持续关注这个主题
              </UI.Heading>
            </CardHeader>
            <CardContent>
              <UI.Text size="sm" tone="muted">
                将关键词保存为监控主题，持续跟踪新内容与讨论。
              </UI.Text>
              <Button asChild variant="outline" size="sm" className="mt-4">
                <Link
                  href={
                    params.q
                      ? `/monitors/new?${new URLSearchParams({ q: params.q })}`
                      : "/monitors/new"
                  }
                >
                  存为监控主题
                </Link>
              </Button>
            </CardContent>
          </Card>
        </UI.Content>
      </UI.Content>
    </UI.Content>
  );
}
