import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
import { connection } from "next/server";

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
      <UI.Content>
        <UI.Heading level={1} className="text-3xl font-medium">
          发布管理
        </UI.Heading>
        <UI.Text className="text-muted-foreground mt-4 text-sm leading-7">
          使用独立操作员令牌管理来源公开许可和发布修订。许可收紧立即生效；提高范围后需重建公开投影。
        </UI.Text>
        <PublicationManager />
        <EditorialCorrectionManager initialContentId={contentId} />
      </UI.Content>
    </>
  );
}
