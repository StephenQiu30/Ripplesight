import { PageHeader } from "@/components/system/page-header";
import * as UI from "@/components/ui/content";
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
import { PublicationFailure } from "@/components/publication/reading-parts";

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
        <PublicationFailure error={error} href="/discover/topics" />
      </>
    );
  }
  return (
    <>
      <UI.Content className="flex flex-col gap-y-10">
        <PageHeader
          title={<>行业专题</>}
          description={
            <>围绕明确的主体与技术信号，持续阅读当前可公开的精选材料。</>
          }
        />
        {groups.map(([group, label]) => (
          <UI.Content as="section" key={group}>
            <UI.Heading level={2} className="mb-4 text-lg font-medium">
              {label}
            </UI.Heading>
            <UI.Content className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {directory.topics
                .filter((topic) => topic.group === group)
                .map((topic) => (
                  <Item asChild variant="outline" key={topic.slug}>
                    <Link href={`/discover/topics/${topic.slug}`}>
                      <ItemContent className="min-w-0 gap-3">
                        <ItemTitle>
                          <UI.Heading level={3}>{topic.name}</UI.Heading>
                        </ItemTitle>
                        <ItemDescription className="line-clamp-none">
                          {topic.definition}
                        </ItemDescription>
                        <UI.Text className="mt-4 text-xs">
                          {topic.total} 篇精选 · 最近 30 天 {topic.recent} 篇
                        </UI.Text>
                      </ItemContent>
                    </Link>
                  </Item>
                ))}
            </UI.Content>
          </UI.Content>
        ))}
      </UI.Content>
    </>
  );
}
