import type { Metadata } from "next";
import { connection } from "next/server";
import { CodexResetManager } from "./components/codex-reset-manager";

export const metadata: Metadata = {
  title: "公告配置与复核",
  robots: { index: false, follow: false },
};
export default async function CodexResetManagePage() {
  await connection();
  return <CodexResetManager />;
}
