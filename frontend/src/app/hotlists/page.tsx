import type { Metadata } from "next";
import { Suspense } from "react";
import { connection } from "next/server";

import { HotlistWorkspace } from "./components/hotlist-workspace";

export const metadata: Metadata = {
  title: "热榜历史",
  robots: { index: false, follow: false },
};

export default async function HotlistsPage() {
  await connection();
  return (
    <Suspense fallback={<p className="px-5 py-12">正在读取热榜历史…</p>}>
      <HotlistWorkspace />
    </Suspense>
  );
}
