import * as UI from "@/components/ui/content";
import type { Metadata } from "next";
import { connection } from "next/server";
import { SavedItems } from "@/components/publication/local-reading";
export const metadata: Metadata = {
  title: "本机收藏",
  robots: { index: false, follow: false },
};
export default async function StarredPage() {
  await connection();
  return (
    <>
      <UI.Content>
        <UI.Heading level={1} className="mb-8 text-3xl font-medium">
          收藏与阅读记录
        </UI.Heading>
        <SavedItems full />
      </UI.Content>
    </>
  );
}
