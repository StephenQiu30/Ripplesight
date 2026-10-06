import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
import { connection } from "next/server";
import { SavedItems } from "@/components/publication/local-reading";
import { categories } from "@/components/publication/reading-format";
export const metadata: Metadata = {
  title: "本机收藏",
  robots: { index: false, follow: false },
};
export default async function StarredPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  await connection();
  const params = await searchParams;
  const category =
    categories.find(([key]) => key === params.category)?.[0] ??
    (params.category === "uncategorized" ? "uncategorized" : "all");
  const requestedPage = Number(params.page);
  const page =
    Number.isSafeInteger(requestedPage) && requestedPage > 0
      ? requestedPage
      : 1;
  return (
    <UI.Content layout="stack" className="gap-8">
      <UI.Content as="header" layout="stack" className="gap-2">
        <UI.Heading level={1}>本机收藏</UI.Heading>
        <UI.Text tone="muted" size="sm">
          保存值得回看的资讯，继续阅读本机记录。
        </UI.Text>
      </UI.Content>
      <SavedItems
        key={JSON.stringify(params)}
        full
        initialCategory={category}
        initialView={params.view === "read" ? "read" : "saved"}
        initialPage={page}
      />
    </UI.Content>
  );
}
