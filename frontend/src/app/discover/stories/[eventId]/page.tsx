import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { getPublicStory } from "@/api/gongkaifabu";
import { PosterDownload } from "@/components/publication/poster-download";
import { ApiRequestError } from "@/request";
import {
  PublicationFailure,
  PublicationNavigation,
  PublicItemCards,
  publicationTime,
} from "@/components/publication/reading-parts";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ eventId: string }>;
}): Promise<Metadata> {
  const { eventId } = await params;
  try {
    const story = await getPublicStory({ event_id: eventId });
    return {
      title: story.title,
      description: story.summary,
      robots: { index: story.indexable, follow: story.indexable },
      alternates: { canonical: story.canonical_url ?? undefined },
      openGraph: {
        title: story.title,
        description: story.summary,
        type: "article",
        images: story.canonical_url
          ? [
              {
                url: new URL(`/og/stories/${story.id}.png`, story.canonical_url)
                  .href,
                width: 1200,
                height: 630,
              },
            ]
          : undefined,
      },
    };
  } catch {
    return { title: "公开事件", robots: { index: false, follow: false } };
  }
}

export default async function PublicStoryPage({
  params,
}: {
  params: Promise<{ eventId: string }>;
}) {
  await connection();
  const { eventId } = await params;
  let story: HotKeyAPI.PublicStoryView;
  try {
    story = await getPublicStory({ event_id: eventId });
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) notFound();
    return (
      <>
        <PublicationNavigation />
        <PublicationFailure error={error} href="/discover" />
      </>
    );
  }
  return (
    <>
      <PublicationNavigation />
      <div className="space-y-8">
        <div className="text-muted-foreground flex flex-wrap gap-4 text-sm">
          <time dateTime={story.first_seen_at}>
            {publicationTime(story.first_seen_at)}
          </time>
          <span>
            {
              { active: "持续发展", watching: "观察中", settled: "已收束" }[
                story.phase
              ]
            }
          </span>
          <span>修订 {story.revision}</span>
          {story.heat !== null && story.heat !== undefined ? (
            <span>热度 {story.heat.toFixed(2)}</span>
          ) : null}
        </div>
        <h1 className="text-3xl leading-tight font-medium">{story.title}</h1>
        <p className="text-muted-foreground leading-8">{story.summary}</p>
        {story.latest_progress ? (
          <section className="space-y-3">
            <h2 className="text-lg font-medium">最新进展</h2>
            <p className="leading-7">{story.latest_progress}</p>
          </section>
        ) : null}
        <PosterDownload target={{ eventId: story.id }} />
        <section>
          <h2 className="text-xl font-medium">来源与报道</h2>
          <PublicItemCards items={story.reports} />
        </section>
      </div>
    </>
  );
}
