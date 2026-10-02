import type { Metadata } from "next";
import { connection } from "next/server";
import { CodexResetWorkspace } from "./components/codex-reset-workspace";

export const metadata: Metadata = {
  title: "Codex 重置公告",
  robots: { index: false, follow: false },
};

export default async function CodexResetsPage() {
  await connection();
  return <CodexResetWorkspace />;
}
