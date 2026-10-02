import type { Metadata } from "next";
import { connection } from "next/server";
import { publicSiteMetadata } from "@/components/publication/site-metadata";

import { getLeaderboardRules } from "@/api/moxingbang";
import { RulesReading } from "@/app/leaderboard/rules/components/rules-reading";
import { LeaderboardFailure } from "@/components/leaderboard/reading-parts";

export async function generateMetadata(): Promise<Metadata> {
  let indexable = false;
  try {
    const data = await getLeaderboardRules({
      baseURL: process.env.HOTKEY_API_ORIGIN ?? "http://127.0.0.1:8867",
    });
    indexable = Boolean(data.methodology_version && data.budgets.length);
  } catch {
    // Do not index a failed rules read.
  }
  return publicSiteMetadata({
    title: "模型榜计算规则",
    path: "/leaderboard/rules",
    imagePath: "/og/pages/leaderboard.png",
    indexable,
  });
}

export default async function LeaderboardRulesPage() {
  await connection();
  let data: HotKeyAPI.RulesView;
  try {
    data = await getLeaderboardRules({
      baseURL: process.env.HOTKEY_API_ORIGIN ?? "http://127.0.0.1:8867",
    });
  } catch (error) {
    return <LeaderboardFailure error={error} href="/leaderboard/rules" />;
  }
  return <RulesReading data={data} />;
}
