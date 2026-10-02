"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpenIcon, ChevronDownIcon } from "lucide-react";
import { useRef, useState } from "react";

import { BrandLockup } from "@/components/brand/brand-lockup";
import { AccountMenu } from "@/components/auth/account-menu";
import { isPublicPagePath } from "@/components/auth/access";
import { useIdentitySession } from "@/components/auth/session-context";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LayoutContainer } from "./layout-container";
import { UsageGuide } from "./usage-guide";

const destinations = [
  { href: "/topics", label: "我的关注", paths: ["/topics", "/monitors"] },
  { href: "/events", label: "事件", paths: ["/events"] },
  { href: "/content", label: "相关内容", paths: ["/content"] },
  { href: "/hotlists", label: "热榜", paths: ["/hotlists"] },
  {
    href: "/discover",
    label: "资讯",
    paths: ["/discover", "/items", "/feeds", "/agent", "/publication"],
  },
  { href: "/discover/topics", label: "行业主题", paths: ["/discover/topics"] },
  { href: "/editions", label: "日周月刊", paths: ["/editions"] },
  {
    href: "/reports/daily",
    label: "公开刊物",
    paths: ["/reports/daily", "/reports/weekly", "/reports/monthly"],
  },
  { href: "/sources", label: "来源设置", paths: ["/sources"] },
  {
    href: "/editorial-sources",
    label: "编辑来源",
    paths: ["/editorial-sources"],
  },
  { href: "/operations", label: "运营管理", paths: ["/operations"] },
  {
    href: "/operations/models",
    label: "模型能力配置",
    paths: ["/operations/models"],
  },
  { href: "/jobs", label: "采集记录", paths: ["/jobs"] },
  { href: "/reports", label: "已有报告", paths: ["/reports"] },
  { href: "/leaderboard", label: "模型榜", paths: ["/leaderboard"] },
  { href: "/codex-resets", label: "Codex 公告", paths: ["/codex-resets"] },
  {
    href: "/about",
    label: "关于与联系",
    paths: [
      "/about",
      "/changelog",
      "/privacy",
      "/terms",
      "/contact",
      "/feedback",
    ],
  },
  { href: "/site/manage", label: "站点设置", paths: ["/site/manage"] },
];

export function BasicHeader() {
  const pathname = usePathname();
  const session = useIdentitySession();
  const workspace = !!session && !isPublicPagePath(pathname);
  const [guideOpen, setGuideOpen] = useState(false);
  const guideTriggerRef = useRef<HTMLButtonElement>(null);
  const current = destinations
    .flatMap((destination) =>
      destination.paths.map((path) => ({ destination, path })),
    )
    .filter(({ path }) => pathname === path || pathname?.startsWith(`${path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0]?.destination;

  return (
    <>
      <header className="layout-region bg-background shrink-0 overflow-hidden print:hidden">
        <LayoutContainer className="flex h-20 items-center justify-between gap-4">
          <BrandLockup href="/" compactOnMobile />
          <nav
            aria-label={workspace ? "工作区导航" : "站点导航"}
            className="flex min-w-0 items-center gap-1 sm:gap-2"
          >
            {workspace ? (
              <>
                <div className="hidden items-center gap-1 md:flex">
                  {destinations.slice(0, 4).map((destination) => (
                    <Button
                      key={destination.href}
                      asChild
                      variant={current === destination ? "secondary" : "ghost"}
                      size="navigation"
                    >
                      <Link
                        href={destination.href}
                        aria-current={
                          current === destination ? "page" : undefined
                        }
                      >
                        {destination.label}
                      </Link>
                    </Button>
                  ))}
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="navigation"
                      aria-label="更多页面"
                    >
                      <span className="md:hidden">菜单</span>
                      <span className="hidden md:inline">更多</span>
                      <ChevronDownIcon data-icon="inline-end" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="min-w-44">
                    <DropdownMenuGroup>
                      {destinations.map((destination, index) => (
                        <DropdownMenuItem
                          key={destination.href}
                          asChild
                          className={index < 4 ? "md:hidden" : undefined}
                        >
                          <Link
                            href={destination.href}
                            aria-current={
                              current === destination ? "page" : undefined
                            }
                          >
                            {destination.label}
                          </Link>
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuGroup>
                  </DropdownMenuContent>
                </DropdownMenu>
              </>
            ) : (
              <>
                <Button
                  asChild
                  variant="ghost"
                  size="navigation"
                  className="hidden sm:inline-flex"
                >
                  <Link href="/about">关于</Link>
                </Button>
              </>
            )}
            <Button
              ref={guideTriggerRef}
              variant="ghost"
              size="navigation"
              aria-label="使用指南"
              onClick={() => setGuideOpen(true)}
            >
              <BookOpenIcon data-icon="inline-start" />
              <span className="hidden lg:inline">使用指南</span>
            </Button>
            {workspace ? (
              <AccountMenu />
            ) : (
              <Button asChild size="navigation">
                <Link href={session ? "/topics" : "/login"}>
                  {session ? "进入系统" : "登录"}
                </Link>
              </Button>
            )}
          </nav>
        </LayoutContainer>
      </header>
      <UsageGuide
        view={guideOpen ? "guide" : null}
        onClose={() => setGuideOpen(false)}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          guideTriggerRef.current?.focus();
        }}
      />
    </>
  );
}
