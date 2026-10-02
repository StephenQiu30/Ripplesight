import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { getPublicTopicPage } from "@/api/gongkaifabu";
import { getPublicSiteMeta } from "@/api/zhandiziliao";
import { ApiRequestError } from "@/request";
import {
  PublicItemCards,
  PublicationFailure,
  PublicationNavigation,
} from "@/components/publication/reading-parts";
import { Button } from "@/components/ui/button";
export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  try {
    const [page, site] = await Promise.all([
      getPublicTopicPage({ slug, page: 1 }),
      getPublicSiteMeta(),
    ]);
    return {
      title: page.topic.name,
      description: page.topic.definition,
      robots: { index: page.topic.indexable, follow: page.topic.indexable },
      alternates: {
        canonical: `${site.public_base_url}/discover/topics/${encodeURIComponent(slug)}`,
      },
      openGraph: {
        title: page.topic.name,
        description: page.topic.definition,
        images: [
          {
            url: `${site.public_base_url}/og/topics/${encodeURIComponent(slug)}.png`,
            width: 1200,
            height: 630,
          },
        ],
      },
    };
  } catch {
    return { title: "专题精选", robots: { index: false, follow: false } };
  }
}
export default async function TopicPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  await connection();
  const { slug } = await params;
  const raw = (await searchParams).page;
  const number = raw && /^[1-9][0-9]{0,5}$/.test(raw) ? Number(raw) : 1;
  let page: HotKeyAPI.PublicTopicPageView;
  try {
    page = await getPublicTopicPage({ slug, page: number });
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) notFound();
    return (
      <>
        <PublicationNavigation />
        <PublicationFailure
          error={error}
          href={`/discover/topics/${encodeURIComponent(slug)}`}
        />
      </>
    );
  }
  return (
    <>
      <PublicationNavigation />
      <div>
        <Link href="/discover/topics" className="text-muted-foreground text-sm">
          ← 全部专题
        </Link>
        <h1 className="mt-6 text-3xl font-medium">{page.topic.name}</h1>
        <p className="text-muted-foreground mt-3 leading-7">
          {page.topic.definition}
        </p>
        <p className="text-muted-foreground mt-3 text-sm">
          {page.topic.total} 篇精选 · 最近 30 天 {page.topic.recent} 篇
        </p>
        {page.related.length ? (
          <nav
            aria-label="相关专题"
            className="mt-5 flex flex-wrap gap-4 text-sm"
          >
            {page.related.map((topic) => (
              <Link key={topic.slug} href={`/discover/topics/${topic.slug}`}>
                {topic.name}
              </Link>
            ))}
          </nav>
        ) : null}
        <PublicItemCards items={page.items} />
        <nav aria-label="专题分页" className="mt-7 flex items-center gap-4">
          {page.page > 1 ? (
            <Button variant="outline" asChild>
              <Link href={`/discover/topics/${slug}?page=${page.page - 1}`}>
                上一页
              </Link>
            </Button>
          ) : null}
          <span className="text-muted-foreground text-sm">
            第 {page.page} / {page.page_count} 页
          </span>
          {page.page < page.page_count ? (
            <Button variant="outline" asChild>
              <Link href={`/discover/topics/${slug}?page=${page.page + 1}`}>
                下一页
              </Link>
            </Button>
          ) : null}
        </nav>
      </div>
    </>
  );
}
