import type { Metadata } from "next";
import { connection } from "next/server";
import { EditionList } from "./components/edition-list";

export const metadata: Metadata = {
  title: "日周月刊",
  robots: { index: false, follow: false },
};

export default async function EditionsPage() {
  await connection();
  return <EditionList />;
}
