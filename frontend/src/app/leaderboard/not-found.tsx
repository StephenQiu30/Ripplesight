import Link from "next/link";
import { PageState } from "@/components/system/page-state";
import { LeaderboardRouteFrame } from "@/components/leaderboard/route-frame";
import { Button } from "@/components/ui/button";

export default function LeaderboardNotFound() {
  return (
    <LeaderboardRouteFrame>
      <PageState
        headingLevel={2}
        state="empty"
        eyebrow="未找到"
        title="没有这项榜单或公开记录"
        description="请返回模型榜，或通过侧栏查看评测来源与计算规则。"
        action={
          <Button asChild>
            <Link href="/leaderboard">返回模型榜</Link>
          </Button>
        }
      />
    </LeaderboardRouteFrame>
  );
}
