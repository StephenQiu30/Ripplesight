"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookmarkIcon,
  BookOpenIcon,
  ChartNoAxesColumnIcon,
  CompassIcon,
  HomeIcon,
  LayoutDashboardIcon,
  MoreHorizontalIcon,
  PlusIcon,
  RssIcon,
  UserRoundIcon,
} from "lucide-react";
import { AccountMenu } from "@/components/auth/account-menu";
import { useIdentitySession } from "@/components/auth/session-context";
import { BrandLockup } from "@/components/brand/brand-lockup";
import { Button } from "@/components/ui/button";
import { Content, Text } from "@/components/ui/content";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
} from "@/components/ui/navigation-menu";
import { ThemeMenuItems, ThemeToggle } from "./theme-toggle";

const destinations = [
  { href: "/", label: "首页", icon: HomeIcon, match: ["/"] },
  {
    href: "/discover?mode=all",
    label: "探索资讯",
    icon: RssIcon,
    match: ["/discover", "/items"],
  },
  {
    href: "/discover/topics",
    label: "专题",
    icon: CompassIcon,
    match: ["/discover/topics"],
  },
  {
    href: "/discover/starred",
    label: "本机收藏",
    icon: BookmarkIcon,
    match: ["/discover/starred"],
  },
  {
    href: "/reports/weekly",
    label: "日周月刊",
    icon: BookOpenIcon,
    match: ["/reports/daily", "/reports/weekly", "/reports/monthly"],
  },
  {
    href: "/leaderboard",
    label: "模型榜",
    icon: ChartNoAxesColumnIcon,
    match: ["/leaderboard"],
  },
];

export function BasicSidebar() {
  const pathname = usePathname() ?? "/";
  const session = useIdentitySession();
  const links = session
    ? [
        ...destinations,
        {
          href: "/workspace",
          label: "工作台",
          icon: LayoutDashboardIcon,
          match: [
            "/workspace",
            "/topics",
            "/monitors",
            "/reports",
            "/jobs",
            "/content",
            "/events",
            "/sources",
            "/operations",
            "/publication",
            "/editorial-sources",
            "/feeds",
            "/hotlists",
            "/alerts",
            "/account",
            "/site",
            "/editions",
            "/agent",
          ],
        },
      ]
    : destinations;
  const current = links
    .flatMap((destination) =>
      destination.match
        .filter(
          (path) =>
            pathname === path ||
            (path !== "/" && pathname.startsWith(`${path}/`)),
        )
        .map((path) => ({ href: destination.href, length: path.length })),
    )
    .sort((a, b) => b.length - a.length)[0]?.href;
  const personalHref = session ? "/workspace" : "/login?returnTo=%2Fworkspace";

  const more = (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="rail"
          className="w-full justify-center rounded-full px-3 lg:justify-start"
          aria-label="更多导航"
        >
          <MoreHorizontalIcon data-icon="inline-start" />
          <Text as="span" className="hidden lg:inline">
            更多
          </Text>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56" aria-label="更多导航">
        <DropdownMenuGroup>
          {links
            .filter(({ href }) => href !== "/")
            .map(({ href, label, icon: Icon }) => (
              <DropdownMenuItem key={href} asChild>
                <Link href={href}>
                  <Icon aria-hidden="true" />
                  {label}
                </Link>
              </DropdownMenuItem>
            ))}
          <DropdownMenuItem asChild>
            <Link href="/about">关于知微见澜</Link>
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <Link href="/feedback">意见反馈</Link>
          </DropdownMenuItem>
          {session ? (
            <DropdownMenuItem asChild>
              <Link href="/account">账户设置</Link>
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem asChild>
              <Link href="/login">登录</Link>
            </DropdownMenuItem>
          )}
        </DropdownMenuGroup>
        <Content className="md:hidden">
          <ThemeMenuItems />
        </Content>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  return (
    <Content
      as="aside"
      aria-label="站点侧边栏"
      className="flex shrink-0 flex-col md:w-20 lg:w-60 xl:w-64 print:hidden"
    >
      <Content className="hidden h-full min-h-0 flex-col px-2 py-4 md:flex lg:px-4">
        <Content className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto">
          <Content className="flex-none overflow-hidden px-2">
            <BrandLockup href="/" rail />
          </Content>
          <NavigationMenu
            viewport={false}
            aria-label="站点导航"
            className="w-full max-w-none flex-none items-start"
          >
            <NavigationMenuList className="w-full flex-col items-stretch gap-1">
              {links.map(({ href, label, icon: Icon }) => (
                <NavigationMenuItem key={href}>
                  <NavigationMenuLink
                    asChild
                    size="rail"
                    active={current === href}
                    className="justify-center px-3 lg:justify-start"
                  >
                    <Link
                      href={href}
                      aria-label={label}
                      aria-current={current === href ? "page" : undefined}
                    >
                      <Icon aria-hidden="true" />
                      <Text as="span" className="hidden lg:inline">
                        {label}
                      </Text>
                    </Link>
                  </NavigationMenuLink>
                </NavigationMenuItem>
              ))}
              <NavigationMenuItem>{more}</NavigationMenuItem>
            </NavigationMenuList>
          </NavigationMenu>
          <Button
            asChild
            size="xl"
            className="w-full flex-none rounded-full px-3"
          >
            <Link
              href={personalHref}
              aria-label={session ? "管理个人关注" : "定制我的关注"}
            >
              <PlusIcon data-icon="inline-start" />
              <Text as="span" className="hidden lg:inline">
                {session ? "管理个人关注" : "定制我的关注"}
              </Text>
            </Link>
          </Button>
        </Content>
        <Content className="flex flex-none flex-wrap items-center justify-center gap-2 pt-4 lg:justify-between">
          {session ? (
            <AccountMenu />
          ) : (
            <Button
              asChild
              variant="ghost"
              size="xl"
              className="min-w-0 rounded-full px-3"
            >
              <Link href="/login">
                <UserRoundIcon data-icon="inline-start" />
                <Text as="span" className="hidden lg:inline">
                  登录账户
                </Text>
              </Link>
            </Button>
          )}
          <ThemeToggle />
        </Content>
      </Content>
      <NavigationMenu
        viewport={false}
        aria-label="手机导航"
        className="bg-background fixed inset-x-0 bottom-0 z-30 w-full max-w-none border-t px-2 pb-2 md:hidden"
      >
        <NavigationMenuList className="w-full justify-between">
          {[destinations[0], destinations[1], destinations[3]].map(
            ({ href, label, icon: Icon }) => (
              <NavigationMenuItem key={href} className="flex-1">
                <NavigationMenuLink
                  asChild
                  size="mobile"
                  active={current === href}
                >
                  <Link
                    href={href}
                    aria-label={label}
                    aria-current={current === href ? "page" : undefined}
                  >
                    <Icon aria-hidden="true" />
                  </Link>
                </NavigationMenuLink>
              </NavigationMenuItem>
            ),
          )}
          <NavigationMenuItem className="flex-1">
            <Button asChild variant="ghost" size="xl" className="w-full px-3">
              <Link href={personalHref} aria-label="个人工作台">
                <UserRoundIcon data-icon="inline-start" />
              </Link>
            </Button>
          </NavigationMenuItem>
          <NavigationMenuItem className="flex-1">{more}</NavigationMenuItem>
        </NavigationMenuList>
      </NavigationMenu>
    </Content>
  );
}
