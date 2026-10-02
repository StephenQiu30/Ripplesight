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
  PublicationFailure,
  PublicationNavigation,
} from "@/components/publication/reading-parts";
import { PublicTimelineCards } from "@/components/publication/reading-groups";
import { SavedItems } from "@/components/publication/local-reading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
      const page = await getPublicReadingTimeline({
        window: "24h",
        channel: "all",
        limit: 20,
      });
      indexable =
        page.cards.length > 0 &&
        page.cards.every((card) => card.item.indexable === true);
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
  const mode = params.mode === "all" ? "all" : "selected";
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
      <main className="mx-auto max-w-6xl px-5 py-10 sm:px-8">
        <h1 className="text-3xl font-medium tracking-tight">值得关注的资讯</h1>
        <form method="get" className="my-7 flex flex-wrap items-end gap-3">
          <label className="space-y-2 text-xs">
            范围
            <select
              name="mode"
              defaultValue={mode}
              className="bg-muted block rounded-md p-2 text-sm"
            >
              <option value="selected">精选</option>
              <option value="all">全部</option>
            </select>
          </label>
          <label className="space-y-2 text-xs">
            时间
            <select
              name="window"
              defaultValue={window}
              className="bg-muted block rounded-md p-2 text-sm"
            >
              <option value="24h">24 小时</option>
              <option value="7d">7 天</option>
            </select>
          </label>
          <label className="space-y-2 text-xs">
            分类
            <select
              name="category"
              defaultValue={category ?? ""}
              className="bg-muted block rounded-md p-2 text-sm"
            >
              <option value="">全部分类</option>
              {categories.map(([key, label]) => (
                <option value={key} key={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-2 text-xs">
            频道
            <select
              name="channel"
              defaultValue={channel ?? ""}
              className="bg-muted block rounded-md p-2 text-sm"
            >
              <option value="">全部频道</option>
              <option value="news">资讯</option>
              <option value="x">X</option>
              <option value="firstParty">第一方</option>
            </select>
          </label>
          <label className="space-y-2 text-xs">
            排列
            <select
              name="by"
              defaultValue={by}
              className="bg-muted block rounded-md p-2 text-sm"
            >
              <option value="timeline">发现时间线</option>
              <option value="published">来源发布时间</option>
            </select>
          </label>
          <label className="space-y-2 text-xs">
            来源
            <Input
              name="source_key"
              defaultValue={params.source_key}
              maxLength={64}
              placeholder="来源标识"
            />
          </label>
          <label className="min-w-40 flex-1 space-y-2 text-xs">
            标签
            <Input
              name="tag"
              defaultValue={params.tag}
              maxLength={128}
              placeholder="正式标签"
            />
          </label>
          <label className="min-w-40 flex-1 space-y-2 text-xs">
            专题
            <Input
              name="topic"
              defaultValue={params.topic}
              maxLength={64}
              placeholder="专题标识，如 openai"
            />
          </label>
          <label className="space-y-2 text-xs">
            搜索排序
            <select
              name="search_order"
              defaultValue={
                params.search_order === "time" ? "time" : "relevance"
              }
              className="bg-muted block rounded-md p-2 text-sm"
            >
              <option value="relevance">相关性</option>
              <option value="time">最新时间</option>
            </select>
          </label>
          <label className="min-w-40 flex-1 space-y-2 text-xs">
            检索
            <Input
              name="q"
              defaultValue={params.q}
              maxLength={200}
              placeholder="所有词项均匹配"
            />
          </label>
          <Button type="submit">查看</Button>
        </form>
        <div className="grid gap-12 lg:grid-cols-3">
          <section className="lg:col-span-2">
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
          </section>
          <aside className="space-y-10">
            <section>
              <h2 className="font-medium">事件热度</h2>
              {hot?.stories.length ? (
                <ul className="mt-4 space-y-5">
                  {hot.stories.map((story) => (
                    <li key={story.id}>
                      <Link
                        href={`/discover/stories/${story.id}`}
                        className="text-sm leading-6 font-medium"
                      >
                        {story.title}
                      </Link>
                      <p className="text-muted-foreground mt-1 text-xs">
                        热度 {story.heat?.toFixed(1) ?? "未知"} ·{" "}
                        {story.attention?.participant_count ?? 0} 个参与方
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground mt-4 text-sm">
                  暂无符合热度条件的公开事件。
                </p>
              )}
            </section>
            <SavedItems />
          </aside>
        </div>
      </main>
    </>
  );
}
