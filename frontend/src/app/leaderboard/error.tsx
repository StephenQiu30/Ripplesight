"use client";

import { PageState } from "@/components/system/page-state";
import { LeaderboardRouteFrame } from "@/components/leaderboard/route-frame";
import { Button } from "@/components/ui/button";

export default function LeaderboardError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <LeaderboardRouteFrame>
      <PageState
        headingLevel={2}
        state="error"
        eyebrow="模型榜"
        title="模型榜页面未完成加载"
        description="请重试；也可以通过侧栏查看来源与计算规则。"
        action={<Button onClick={reset}>重新加载</Button>}
      />
    </LeaderboardRouteFrame>
  );
}
