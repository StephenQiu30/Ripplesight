import Link from "next/link";
import { ChevronDownIcon } from "lucide-react";

import { BrandLockup } from "@/components/brand/brand-lockup";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const destinations = [
  { key: "topics", href: "/topics", label: "我的关注" },
  { key: "events", href: "/events", label: "事件" },
  { key: "content", href: "/content", label: "相关内容" },
  { key: "hotlists", href: "/hotlists", label: "热榜" },
  { key: "discover", href: "/discover", label: "资讯" },
  { key: "industry-topics", href: "/discover/topics", label: "行业主题" },
  { key: "editions", href: "/editions", label: "日周月刊" },
  { key: "public-editions", href: "/reports/daily", label: "公开刊物" },
  { key: "sources", href: "/sources", label: "来源设置" },
  { key: "editorial-sources", href: "/editorial-sources", label: "编辑来源" },
  { key: "operations", href: "/operations", label: "运营管理" },
  { key: "models", href: "/operations/models", label: "模型能力配置" },
  { key: "jobs", href: "/jobs", label: "采集记录" },
  { key: "reports", href: "/reports", label: "已有报告" },
  { key: "leaderboard", href: "/leaderboard", label: "模型榜" },
  { key: "codex-resets", href: "/codex-resets", label: "Codex 公告" },
  { key: "site", href: "/about", label: "关于与联系" },
  { key: "site-settings", href: "/site/manage", label: "站点设置" },
] as const;

type WorkspaceHeaderProps = {
  current: (typeof destinations)[number]["key"];
};

export function WorkspaceHeader({ current }: WorkspaceHeaderProps) {
  return (
    <header className="mx-auto flex min-h-20 max-w-6xl items-center justify-between gap-4 px-5 sm:px-8">
      <BrandLockup href="/" compactOnMobile />
      <nav aria-label="工作区导航" className="flex items-center gap-2">
        <div className="hidden items-center gap-1 md:flex">
          {destinations.slice(0, 4).map((destination) => (
            <Button
              key={destination.key}
              asChild
              variant={current === destination.key ? "secondary" : "ghost"}
              size="navigation"
            >
              <Link
                href={destination.href}
                aria-current={current === destination.key ? "page" : undefined}
              >
                {destination.label}
              </Link>
            </Button>
          ))}
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="navigation">
              <span className="md:hidden">
                {
                  destinations.find(
                    (destination) => destination.key === current,
                  )?.label
                }
              </span>
              <span className="hidden md:inline">更多</span>
              <ChevronDownIcon data-icon="inline-end" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-44">
            <DropdownMenuGroup>
              {destinations.map((destination, index) => (
                <DropdownMenuItem
                  key={destination.key}
                  asChild
                  className={index < 4 ? "md:hidden" : undefined}
                >
                  <Link
                    href={destination.href}
                    aria-current={
                      current === destination.key ? "page" : undefined
                    }
                  >
                    {destination.label}
                  </Link>
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </nav>
    </header>
  );
}
