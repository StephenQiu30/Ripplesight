import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { getPublicStory } from "@/api/gongkaifabu";
import { PublicStoryReading } from "./components/public-story-reading";
import { ApiRequestError } from "@/request";
import { PublicationFailure } from "@/components/publication/reading-parts";

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
    <PublicStoryReading key={`${story.id}:${story.revision}`} story={story} />
  );
}
