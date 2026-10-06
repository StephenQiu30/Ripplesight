import { PageState } from "@/components/system/page-state";
import { LeaderboardRouteFrame } from "@/components/leaderboard/route-frame";

export default function LeaderboardLoading() {
  return (
    <LeaderboardRouteFrame>
      <PageState
        headingLevel={2}
        state="loading"
        eyebrow="模型榜"
        title="正在读取模型榜"
        description="正在读取已发布排名、评测来源或计算规则。"
      />
    </LeaderboardRouteFrame>
  );
}
