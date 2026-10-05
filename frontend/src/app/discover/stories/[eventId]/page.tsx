import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { getPublicStory } from "@/api/gongkaifabu";
import { PosterDownload } from "@/components/publication/poster-download";
import { ApiRequestError } from "@/request";
import {
  PublicationFailure,
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
      robots: { index: false, follow: false },
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
        <PublicationFailure error={error} href="/discover" />
      </>
    );
  }
  return (
    <>
      <UI.Content className="flex flex-col gap-y-8">
        <UI.Content className="text-muted-foreground flex flex-wrap gap-4 text-sm">
          <UI.Timestamp dateTime={story.first_seen_at}>
            {publicationTime(story.first_seen_at)}
          </UI.Timestamp>
          <UI.Text as="span">
            {
              { active: "持续发展", watching: "观察中", settled: "已收束" }[
                story.phase
              ]
            }
          </UI.Text>
          <UI.Text as="span">修订 {story.revision}</UI.Text>
          {story.heat !== null && story.heat !== undefined ? (
            <UI.Text as="span">热度 {story.heat.toFixed(2)}</UI.Text>
          ) : null}
        </UI.Content>
        <UI.Heading level={1} className="text-3xl leading-tight font-medium">
          {story.title}
        </UI.Heading>
        <UI.Text className="text-muted-foreground leading-8">
          {story.summary}
        </UI.Text>
        {story.latest_progress ? (
          <UI.Content as="section" className="flex flex-col gap-y-3">
            <UI.Heading level={2} className="text-lg font-medium">
              最新进展
            </UI.Heading>
            <UI.Text className="leading-7">{story.latest_progress}</UI.Text>
          </UI.Content>
        ) : null}
        <PosterDownload target={{ eventId: story.id }} />
        <UI.Content as="section">
          <UI.Heading level={2} className="text-xl font-medium">
            来源与报道
          </UI.Heading>
          <PublicItemCards items={story.reports} />
        </UI.Content>
      </UI.Content>
    </>
  );
}
