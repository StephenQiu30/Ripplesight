import {
  Item,
  ItemContent,
  ItemTitle,
  ItemDescription,
} from "@/components/ui/item";
import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { getPublicTopicDirectory } from "@/api/gongkaifabu";
import {
  PublicationFailure,
  PublicationNavigation,
} from "@/components/publication/reading-parts";

export const metadata: Metadata = {
  title: "行业专题",
  robots: { index: false, follow: false },
};
const groups = [
  ["company", "公司与机构"],
  ["field", "研究与技术"],
  ["genre", "内容类型"],
] as const;
export default async function PublicTopicsPage() {
  await connection();
  let directory: HotKeyAPI.PublicTopicDirectoryView;
  try {
    directory = await getPublicTopicDirectory();
  } catch (error) {
    return (
      <>
        <PublicationNavigation />
        <PublicationFailure error={error} href="/discover/topics" />
      </>
    );
  }
  return (
    <>
      <PublicationNavigation />
      <div className="flex flex-col gap-y-10">
        <header>
          <h1 className="text-3xl font-medium">行业专题</h1>
          <p className="text-muted-foreground mt-3 text-sm">
            围绕明确的主体与技术信号，持续阅读当前可公开的精选材料。
          </p>
        </header>
        {groups.map(([group, label]) => (
          <section key={group}>
            <h2 className="mb-4 text-lg font-medium">{label}</h2>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {directory.topics
                .filter((topic) => topic.group === group)
                .map((topic) => (
                  <Item asChild variant="outline" key={topic.slug}>
                    <Link href={`/discover/topics/${topic.slug}`}>
                      <ItemContent className="min-w-0 gap-3">
                        <ItemTitle>
                          <h3>{topic.name}</h3>
                        </ItemTitle>
                        <ItemDescription className="line-clamp-none">
                          {topic.definition}
                        </ItemDescription>
                        <p className="mt-4 text-xs">
                          {topic.total} 篇精选 · 最近 30 天 {topic.recent} 篇
                        </p>
                      </ItemContent>
                    </Link>
                  </Item>
                ))}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
