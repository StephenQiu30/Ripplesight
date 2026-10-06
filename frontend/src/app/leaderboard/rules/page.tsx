import type { Metadata } from "next";
import { connection } from "next/server";
import { publicSiteMetadata } from "@/components/publication/site-metadata";
import { getLeaderboardRules } from "@/api/moxingbang";
import { RulesReading } from "@/app/leaderboard/rules/components/rules-reading";
import { LeaderboardFailure } from "@/components/leaderboard/reading-parts";
import { LeaderboardPageHeader } from "@/components/leaderboard/page-header";
import { Content } from "@/components/ui/content";

export async function generateMetadata(): Promise<Metadata> {
  let indexable = false;
  try {
    const data = await getLeaderboardRules();
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
    data = await getLeaderboardRules();
  } catch (error) {
    return (
      <Content className="flex min-w-0 flex-col gap-6">
        <LeaderboardPageHeader
          title="计算规则与证据边界"
          description="了解公开模型排名的计算方法、固定预算与证据边界。"
        />
        <LeaderboardFailure error={error} href="/leaderboard/rules" />
      </Content>
    );
  }
  return <RulesReading data={data} />;
}
