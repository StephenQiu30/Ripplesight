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
    <SavedItems
      key={JSON.stringify(params)}
      pageTitle
      full
      initialCategory={category}
      initialView={params.view === "read" ? "read" : "saved"}
      initialPage={page}
      initialSort={params.sort === "oldest" ? "oldest" : "recent"}
      initialType={
        ["events", "items", "comments", "editions"].includes(params.type ?? "")
          ? params.type
          : "all"
      }
    />
  );
}
