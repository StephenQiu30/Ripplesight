import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";

import { getSitePublicationItem } from "@/api/gongkaifabu";
import { getPublicSiteMeta } from "@/api/zhandiziliao";
import { PublicationFailure } from "@/components/publication/reading-parts";
import { ItemReader } from "./components/item-reader";
import { ApiRequestError } from "@/request";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ contentId: string }>;
}): Promise<Metadata> {
  const { contentId } = await params;
  let item: HotKeyAPI.PublicItemDetailView;
  try {
    item = await getSitePublicationItem({ content_id: contentId });
    const site = await getPublicSiteMeta();
    return {
      title: item.title,
      description: item.summary ?? undefined,
      robots: { index: false, follow: false },
      alternates: { canonical: site.public_base_url + item.reading_url },
      openGraph: {
        title: item.title,
        description: item.summary ?? undefined,
        type: "article",
        images: [
          {
            url: `${site.public_base_url}/og/items/${item.id}.png`,
            width: 1200,
            height: 630,
          },
        ],
      },
    };
  } catch {
    return { title: "资讯", robots: { index: false, follow: false } };
  }
}

export default async function ItemPage({
  params,
}: {
  params: Promise<{ contentId: string }>;
}) {
  await connection();
  const { contentId } = await params;
  let item: HotKeyAPI.PublicItemDetailView;
  try {
    item = await getSitePublicationItem({ content_id: contentId });
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
      <ItemReader item={item} />
    </>
  );
}
