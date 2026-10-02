import type { Metadata } from "next";
import { connection } from "next/server";
import { EditionDetail } from "../components/edition-detail";

export const metadata: Metadata = {
  title: "刊期详情",
  robots: { index: false, follow: false },
};

export default async function EditionPage({
  params,
}: {
  params: Promise<{ editionId: string }>;
}) {
  await connection();
  const { editionId } = await params;
  return <EditionDetail key={editionId} editionId={editionId} />;
}
