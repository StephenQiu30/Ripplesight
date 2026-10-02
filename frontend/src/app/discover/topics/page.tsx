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
      <main className="mx-auto max-w-6xl space-y-10 px-5 py-10 sm:px-8">
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
                  <Link
                    key={topic.slug}
                    href={`/discover/topics/${topic.slug}`}
                    className="hover:bg-muted/40 rounded-lg border p-5"
                  >
                    <h3 className="font-medium">{topic.name}</h3>
                    <p className="text-muted-foreground mt-2 text-sm leading-6">
                      {topic.definition}
                    </p>
                    <p className="mt-4 text-xs">
                      {topic.total} 篇精选 · 最近 30 天 {topic.recent} 篇
                    </p>
                  </Link>
                ))}
            </div>
          </section>
        ))}
      </main>
    </>
  );
}
