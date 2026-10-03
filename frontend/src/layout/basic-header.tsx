"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CheckIcon, ChevronDownIcon } from "lucide-react";

import { BrandLockup } from "@/components/brand/brand-lockup";
import { AccountMenu } from "@/components/auth/account-menu";
import { isPublicPagePath } from "@/components/auth/access";
import { useIdentitySession } from "@/components/auth/session-context";
import { Button } from "@/components/ui/button";
import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LayoutContainer } from "./layout-container";

const primaryDestinations = [
  { href: "/topics", label: "我的关注", paths: ["/topics", "/monitors"] },
  { href: "/events", label: "事件", paths: ["/events"] },
  { href: "/content", label: "相关内容", paths: ["/content"] },
  { href: "/hotlists", label: "热榜", paths: ["/hotlists"] },
];

const navigationGroups = [
  {
    id: "content",
    label: "内容发现",
    destinations: [
      {
        href: "/discover",
        label: "资讯",
        paths: ["/discover", "/items", "/feeds", "/agent", "/publication"],
      },
      {
        href: "/discover/topics",
        label: "行业主题",
        paths: ["/discover/topics"],
      },
      { href: "/editions", label: "日周月刊", paths: ["/editions"] },
      {
        href: "/reports/daily",
        label: "公开刊物",
        paths: ["/reports/daily", "/reports/weekly", "/reports/monthly"],
      },
      { href: "/reports", label: "已有报告", paths: ["/reports"] },
    ],
  },
  {
    id: "management",
    label: "工作管理",
    destinations: [
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
      { href: "/site/manage", label: "站点设置", paths: ["/site/manage"] },
    ],
  },
  {
    id: "information",
    label: "帮助与信息",
    destinations: [
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
    ],
  },
];

const destinations = [
  ...primaryDestinations,
  ...navigationGroups.flatMap((group) => group.destinations),
];

export function BasicHeader() {
  const pathname = usePathname();
  const session = useIdentitySession();
  const workspace = !!session && !isPublicPagePath(pathname);
  const current = destinations
    .flatMap((destination) =>
      destination.paths.map((path) => ({ destination, path })),
    )
    .filter(({ path }) => pathname === path || pathname?.startsWith(`${path}/`))
    .sort((a, b) => b.path.length - a.path.length)[0]?.destination;

  return (
    <header className="layout-region bg-background shrink-0 overflow-hidden print:hidden">
      <LayoutContainer className="flex h-20 items-center justify-between gap-4">
        <BrandLockup href="/" compactOnMobile />
        <NavigationMenu
          viewport={false}
          aria-label={workspace ? "工作区导航" : "站点导航"}
          className="min-w-0 flex-none"
        >
          <NavigationMenuList className="gap-1 sm:gap-2">
            {workspace ? (
              <>
                {primaryDestinations.map((destination) => (
                  <NavigationMenuItem
                    key={destination.href}
                    className="hidden md:block"
                  >
                    <NavigationMenuLink
                      asChild
                      active={current === destination}
                    >
                      <Link
                        href={destination.href}
                        aria-current={
                          current === destination ? "page" : undefined
                        }
                      >
                        {destination.label}
                      </Link>
                    </NavigationMenuLink>
                  </NavigationMenuItem>
                ))}
                <NavigationMenuItem>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant={
                          current && !primaryDestinations.includes(current)
                            ? "secondary"
                            : "ghost"
                        }
                        size="navigation"
                        aria-label="全部导航"
                      >
                        <span className="md:hidden">菜单</span>
                        <span className="hidden md:inline">全部导航</span>
                        <ChevronDownIcon data-icon="inline-end" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      align="end"
                      sideOffset={8}
                      collisionPadding={16}
                      aria-label="全部导航"
                      className="w-72 max-w-(--radix-dropdown-menu-content-available-width) p-3 md:w-xl"
                    >
                      <div className="grid grid-cols-2 items-start gap-3 md:grid-cols-3 md:gap-4">
                        {[
                          {
                            id: "primary",
                            label: "常用页面",
                            destinations: primaryDestinations,
                          },
                          ...navigationGroups,
                        ].map((group) => (
                          <DropdownMenuGroup
                            key={group.id}
                            aria-labelledby={`header-navigation-${group.id}`}
                            className={
                              group.id === "primary" ? "md:hidden" : undefined
                            }
                          >
                            <DropdownMenuLabel
                              id={`header-navigation-${group.id}`}
                            >
                              {group.label}
                            </DropdownMenuLabel>
                            {group.destinations.map((destination) => (
                              <DropdownMenuItem
                                key={destination.href}
                                asChild
                                className="min-h-11 justify-between gap-2 md:min-h-9"
                              >
                                <Link
                                  href={destination.href}
                                  aria-current={
                                    current === destination ? "page" : undefined
                                  }
                                >
                                  {destination.label}
                                  {current === destination ? (
                                    <CheckIcon aria-hidden="true" />
                                  ) : null}
                                </Link>
                              </DropdownMenuItem>
                            ))}
                          </DropdownMenuGroup>
                        ))}
                      </div>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </NavigationMenuItem>
              </>
            ) : (
              <NavigationMenuItem className="hidden sm:block">
                <NavigationMenuLink asChild>
                  <Link href="/about">关于</Link>
                </NavigationMenuLink>
              </NavigationMenuItem>
            )}
            <NavigationMenuItem>
              {workspace ? (
                <AccountMenu />
              ) : (
                <Button asChild size="navigation">
                  <Link href={session ? "/topics" : "/login"}>
                    {session ? "进入系统" : "登录"}
                  </Link>
                </Button>
              )}
            </NavigationMenuItem>
          </NavigationMenuList>
        </NavigationMenu>
      </LayoutContainer>
    </header>
  );
}
