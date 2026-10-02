import type { Metadata } from "next";
import { connection } from "next/server";
import { SavedItems } from "@/components/publication/local-reading";
import { PublicationNavigation } from "@/components/publication/reading-parts";
export const metadata: Metadata = {
  title: "本机收藏",
  robots: { index: false, follow: false },
};
export default async function StarredPage() {
  await connection();
  return (
    <>
      <PublicationNavigation />
      <main className="mx-auto max-w-4xl px-5 py-10 sm:px-8">
        <h1 className="mb-8 text-3xl font-medium">收藏与阅读记录</h1>
        <SavedItems full />
      </main>
    </>
  );
}
