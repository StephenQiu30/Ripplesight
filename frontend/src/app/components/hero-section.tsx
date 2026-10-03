import Link from "next/link";
import { ArrowUpRightIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useIdentitySession } from "@/components/auth/session-context";

export function HeroSection() {
  const session = useIdentitySession();
  return (
    <section
      aria-label="公开信息平台"
      className="flex flex-col gap-6 pb-10 sm:pb-12 lg:flex-row lg:items-end lg:justify-between lg:gap-12"
    >
      <div className="max-w-2xl">
        <p className="text-muted-foreground mb-4 text-sm">
          知微见澜 · 开放的信息平台
        </p>
        <h1 className="text-3xl leading-tight font-medium tracking-tight sm:text-4xl lg:text-5xl">
          在这里，看见正在发生的变化。
        </h1>
        <p className="text-muted-foreground mt-5 max-w-xl text-base leading-7">
          从最新资讯到事件脉络，沿着来源了解技术、产品与行业。公开内容随时阅读，登录后配置个人关注、查看已有报告。
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <Button asChild>
          <Link href="/discover">
            浏览资讯
            <ArrowUpRightIcon data-icon="inline-end" />
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link href={session ? "/workspace" : "/login?returnTo=%2Fworkspace"}>
            {session ? "我的工作台" : "定制我的关注"}
          </Link>
        </Button>
      </div>
    </section>
  );
}
