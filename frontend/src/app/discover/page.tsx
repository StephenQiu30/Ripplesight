import * as UI from "@/components/ui/content";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import {
  Item,
  ItemContent,
  ItemGroup,
  ItemDescription,
} from "@/components/ui/item";
import { DiscoveryFilters } from "./components/discovery-filters";
import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import {
  getPublicHotStories,
  listPublicItems,
  getPublicReadingTimeline,
} from "@/api/gongkaifabu";
import {
  categories,
  PublicItemCards,
  PublicSourceStatus,
  PublicationFailure,
  PublicationNavigation,
} from "@/components/publication/reading-parts";
import { PublicTimelineCards } from "@/components/publication/reading-groups";
import { SavedItems } from "@/components/publication/local-reading";
import { Button } from "@/components/ui/button";
import { publicSiteMetadata } from "@/components/publication/site-metadata";

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
    title: "资讯",
    path: "/discover",
    imagePath: "/og/pages/hot.png",
    indexable,
  });
}

export default async function DiscoverPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  await connection();
  const params = await searchParams;
  const category = categories.find(([key]) => key === params.category)?.[0];
  const mode = params.mode === "selected" ? "selected" : "all";
  const window = params.window === "7d" ? "7d" : "24h";
  const by = params.by === "published" ? "published" : "timeline";
  const channel =
    params.channel === "news" ||
    params.channel === "x" ||
    params.channel === "firstParty"
      ? params.channel
      : undefined;
  let page: HotKeyAPI.PublicItemsPage;
  let timeline: HotKeyAPI.PublicTimelinePage | null = null;
  let hot: HotKeyAPI.PublicStoriesPage | null = null;
  try {
    if (mode === "selected" && by === "timeline" && !params.q) {
      timeline = await getPublicReadingTimeline({
        window,
        category,
        channel: channel ?? "all",
        source_key: params.source_key || undefined,
        tag: params.tag || undefined,
        topic: params.topic || undefined,
        cursor: params.cursor || undefined,
        limit: 20,
      });
      page = {
        items: timeline.cards.map((card) => card.item),
        next_cursor: timeline.next_cursor,
        snapshot_at: timeline.snapshot_at,
      };
    } else {
      page = await listPublicItems({
        mode,
        window,
        by,
        category,
        channel,
        source_key: params.source_key || undefined,
        tag: params.tag || undefined,
        topic: params.topic || undefined,
        q: params.q || undefined,
        search_order: params.search_order === "time" ? "time" : "relevance",
        cursor: params.cursor || undefined,
        limit: params.q ? 40 : 30,
      });
    }
  } catch (error) {
    return (
      <>
        <PublicationNavigation />
        <PublicationFailure error={error} href="/discover" />
      </>
    );
  }
  try {
    hot = await getPublicHotStories({ limit: 5 });
  } catch {
    /* Lists remain independently readable. */
  }
  const next = new URLSearchParams(
    Object.entries(params).filter((entry): entry is [string, string] =>
      Boolean(entry[1]),
    ),
  );
  if (page.next_cursor) next.set("cursor", page.next_cursor);
  return (
    <>
      <PublicationNavigation />
      <UI.Content>
        <UI.Heading level={1} className="text-3xl font-medium tracking-tight">
          值得关注的资讯
        </UI.Heading>
        <DiscoveryFilters
          key={JSON.stringify(params)}
          mode={mode}
          window={window}
          category={category}
          channel={channel}
          by={by}
          params={params}
          categories={categories}
          sources={Array.from(
            new Map([
              ...(page.source_status ?? []).map(
                (source) =>
                  [
                    source.source_key,
                    { key: source.source_key, name: source.name },
                  ] as const,
              ),
              ...page.items.map(
                (item) =>
                  [
                    item.source.key,
                    { key: item.source.key, name: item.source.name },
                  ] as const,
              ),
            ]).values(),
          )}
        />
        <UI.Content className="grid gap-12 lg:grid-cols-3">
          <UI.Content as="section" className="lg:col-span-2">
            <PublicSourceStatus sources={page.source_status ?? []} />
            {timeline ? (
              <PublicTimelineCards page={timeline} />
            ) : (
              <PublicItemCards items={page.items} />
            )}
            {page.next_cursor ? (
              <Button asChild className="mt-6" variant="outline">
                <Link href={`/discover?${next}`}>下一页</Link>
              </Button>
            ) : null}
          </UI.Content>
          <UI.Content as="aside" className="flex flex-col gap-y-10">
            <UI.Content as="section">
              <UI.Heading level={2} className="font-medium">
                事件热度
              </UI.Heading>
              {hot?.stories.length ? (
                <ItemGroup className="mt-4 flex flex-col gap-y-5">
                  {hot.stories.map((story) => (
                    <Item role="listitem" variant="default" key={story.id}>
                      <ItemContent className="min-w-0 gap-3">
                        <Link
                          href={`/discover/stories/${story.id}`}
                          className="text-sm leading-6 font-medium"
                        >
                          {story.title}
                        </Link>
                        <ItemDescription className="mt-1 line-clamp-none">
                          热度 {story.heat?.toFixed(1) ?? "未知"} ·{" "}
                          {story.attention?.participant_count ?? 0} 个参与方
                        </ItemDescription>
                      </ItemContent>
                    </Item>
                  ))}
                </ItemGroup>
              ) : (
                <Empty className="mt-4">
                  <EmptyHeader>
                    <EmptyDescription>
                      暂无符合热度条件的公开事件。
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
              )}
            </UI.Content>
            <SavedItems />
          </UI.Content>
        </UI.Content>
      </UI.Content>
    </>
  );
}
