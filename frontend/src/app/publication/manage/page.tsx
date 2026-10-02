import type { Metadata } from "next";
import { connection } from "next/server";

import { PublicationNavigation } from "@/components/publication/reading-parts";
import { PublicationManager } from "./components/publication-manager";
import { EditorialCorrectionManager } from "./components/editorial-correction-manager";

export const metadata: Metadata = {
  title: "发布管理",
  robots: { index: false, follow: false },
};

export default async function ManagePublicationPage({
  searchParams,
}: {
  searchParams: Promise<{ content_id?: string }>;
}) {
  await connection();
  const { content_id: contentId } = await searchParams;
  return (
    <>
      <PublicationNavigation />
      <main className="mx-auto max-w-5xl px-5 py-10 sm:px-8">
        <h1 className="text-3xl font-medium">发布管理</h1>
        <p className="text-muted-foreground mt-4 text-sm leading-7">
          使用独立操作员令牌管理来源公开许可和发布修订。许可收紧立即生效；提高范围后需重建公开投影。
        </p>
        <PublicationManager />
        <EditorialCorrectionManager initialContentId={contentId} />
      </main>
    </>
  );
}
