import type { Metadata } from "next";
import { connection } from "next/server";
import { PersonalSourceManager } from "./components/personal-source-manager";

export const metadata: Metadata = {
  title: "我的来源",
  robots: { index: false, follow: false },
};

export default async function PersonalSourcesPage() {
  await connection();
  return <PersonalSourceManager />;
}
