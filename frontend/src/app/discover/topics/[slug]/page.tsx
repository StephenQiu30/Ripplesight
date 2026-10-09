import { PageHeader } from "@/components/system/page-header";
import * as UI from "@/components/ui/content";
import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";
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
} from "@/components/publication/reading-parts";
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
      robots: { index: false, follow: false },
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
        <PublicationFailure
          error={error}
          href={`/discover/topics/${encodeURIComponent(slug)}`}
        />
      </>
    );
  }
  return (
    <>
      <UI.Content>
        <PageHeader
          breadcrumbs={[
            { label: "行业专题", href: "/discover/topics" },
            { label: "专题详情" },
          ]}
          title={<>{page.topic.name}</>}
          description={<>{page.topic.definition}</>}
        />
        <UI.Text className="text-muted-foreground mt-3 text-sm">
          {page.topic.total} 篇精选 · 最近 30 天 {page.topic.recent} 篇
        </UI.Text>
        {page.related.length ? (
          <NavigationMenu
            viewport={false}
            className="mt-5 max-w-full justify-start"
            aria-label="相关专题"
          >
            <NavigationMenuList className="flex-wrap justify-start gap-2">
              {page.related.map((topic) => (
                <NavigationMenuItem key={topic.slug}>
                  <NavigationMenuLink asChild>
                    <Link href={`/discover/topics/${topic.slug}`}>
                      {topic.name}
                    </Link>
                  </NavigationMenuLink>
                </NavigationMenuItem>
              ))}
            </NavigationMenuList>
          </NavigationMenu>
        ) : null}
        <PublicItemCards items={page.items} />
        <NavigationMenu
          viewport={false}
          className="mt-7 max-w-full justify-start"
          aria-label="专题分页"
        >
          <NavigationMenuList className="flex-wrap justify-start gap-2">
            {page.page > 1 ? (
              <NavigationMenuItem>
                <NavigationMenuLink asChild>
                  <Link href={`/discover/topics/${slug}?page=${page.page - 1}`}>
                    上一页
                  </Link>
                </NavigationMenuLink>
              </NavigationMenuItem>
            ) : null}
            <NavigationMenuItem>
              <UI.Text as="span" className="text-muted-foreground text-sm">
                第 {page.page} / {page.page_count} 页
              </UI.Text>
            </NavigationMenuItem>
            {page.page < page.page_count ? (
              <NavigationMenuItem>
                <NavigationMenuLink asChild>
                  <Link href={`/discover/topics/${slug}?page=${page.page + 1}`}>
                    下一页
                  </Link>
                </NavigationMenuLink>
              </NavigationMenuItem>
            ) : null}
          </NavigationMenuList>
        </NavigationMenu>
      </UI.Content>
    </>
  );
}
