import type { Metadata } from "next";
import { connection } from "next/server";
import { WorkspaceCatalog } from "./components/catalog";
export const metadata: Metadata = {
  title: "项目知识库",
  robots: { index: false, follow: false },
};
export default async function Page() {
  await connection();
  return <WorkspaceCatalog />;
}
