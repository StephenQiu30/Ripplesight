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
  const [reading, topics] = await Promise.allSettled([
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
          }
        : reading.value
      : null;
  const currentHref = discoveryHref(params, params.cursor);
  return (
    <UI.Content layout="stack" className="gap-8">
      <UI.Content as="header" layout="stack" className="gap-2">
        <UI.Heading level={1}>探索</UI.Heading>
        <UI.Text tone="muted" size="sm">
          检索当前可公开的资讯，按分类与专题找到值得阅读的内容。
        </UI.Text>
      </UI.Content>
      <DiscoveryFilters
        key={JSON.stringify(params)}
        {...scope}
        params={params}
        categories={categories}
        sources={discoverySources(page)}
      />
      <UI.Content className="grid gap-10 lg:grid-cols-3">
        <UI.Content
          as="section"
          aria-label="搜索结果"
          layout="stack"
          className="min-w-0 lg:col-span-2"
        >
          {page ? (
            <>
              <UI.Text tone="muted" size="xs">
                本页 <UI.InlineCode>{page.items.length}</UI.InlineCode> 条 ·{" "}
                {scope.window === "7d" ? "过去 7 天" : "过去 24 小时"}
              </UI.Text>
              <PublicSourceStatus sources={page.source_status ?? []} />
              <DiscoveryResults page={page} timeline={timeline} />
              {(params.cursor || page.next_cursor) && (
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
        <DiscoveryTopics
          directory={topics.status === "fulfilled" ? topics.value : null}
          error={topics.status === "rejected" ? topics.reason : undefined}
          retryHref={currentHref}
        />
      </UI.Content>
    </UI.Content>
  );
}
