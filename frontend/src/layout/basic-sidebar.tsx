"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BellRingIcon,
  BookmarkIcon,
  BookOpenIcon,
  ChartNoAxesColumnIcon,
  CircleCheckIcon,
  CompassIcon,
  FileTextIcon,
  HomeIcon,
  LayoutDashboardIcon,
  MoreHorizontalIcon,
  PlusIcon,
  RadarIcon,
  SearchIcon,
  UserRoundIcon,
  type LucideIcon,
} from "lucide-react";

import { getReadiness } from "@/api/xitongzhuangtai";
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
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { ThemeMenuItems, ThemeToggle } from "./theme-toggle";

type Destination = {
  href: string;
  label: string;
  icon: LucideIcon;
  match: string[];
};

// 阅读组：公开可见。
const readingDestinations: Destination[] = [
  { href: "/", label: "首页", icon: HomeIcon, match: ["/"] },
  {
    href: "/discover?mode=all",
    label: "探索",
    icon: SearchIcon,
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

// 工作台组：只在有会话时显示。公开刊物的匹配路径更长，会优先于“我的报告”。
const workspaceDestinations: Destination[] = [
  {
    href: "/workspace",
    label: "工作台",
    icon: LayoutDashboardIcon,
    match: [
      "/workspace",
      "/jobs",
      "/content",
      "/events",
      "/sources",
      "/operations",
      "/publication",
      "/editorial-sources",
      "/feeds",
      "/hotlists",
      "/account",
      "/site",
      "/editions",
      "/agent",
    ],
  },
  {
    href: "/topics",
    label: "我的关注",
    icon: RadarIcon,
    match: ["/topics", "/monitors"],
  },
  {
    href: "/alerts",
    label: "突发告警",
    icon: BellRingIcon,
    match: ["/alerts"],
  },
  {
    href: "/reports",
    label: "我的报告",
    icon: FileTextIcon,
    match: ["/reports"],
  },
];

function useNavigation() {
  const pathname = usePathname() ?? "/";
  const session = useIdentitySession();
  const destinations = session
    ? [...readingDestinations, ...workspaceDestinations]
    : readingDestinations;
  const current = destinations
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
  return { session, destinations, current, personalHref };
}

function MoreMenuItems({ mobile = false }: { mobile?: boolean }) {
  const { session, destinations } = useNavigation();
  return (
    <>
      {mobile ? (
        <DropdownMenuGroup>
          {destinations
            .filter(({ href }) => href !== "/")
            .map(({ href, label, icon: Icon }) => (
              <DropdownMenuItem key={href} asChild>
                <Link href={href}>
                  <Icon aria-hidden="true" />
                  {label}
                </Link>
              </DropdownMenuItem>
            ))}
        </DropdownMenuGroup>
      ) : null}
      <DropdownMenuGroup>
        <DropdownMenuItem asChild>
          <Link href="/about">关于Ripplesight</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/feedback">意见反馈</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href={session ? "/account" : "/login"}>
            {session ? "账户设置" : "登录"}
          </Link>
        </DropdownMenuItem>
      </DropdownMenuGroup>
      {mobile ? <ThemeMenuItems /> : null}
    </>
  );
}

function ServiceStatus() {
  const [status, setStatus] = useState<HotKeyAPI.HealthView["status"] | null>(
    null,
  );

  useEffect(() => {
    const controller = new AbortController();
    void getReadiness({ signal: controller.signal }).then(
      (data) => {
        if (
          !controller.signal.aborted &&
          (data?.status === "ready" || data?.status === "ok")
        )
          setStatus(data.status);
      },
      () => {
        if (!controller.signal.aborted) setStatus(null);
      },
    );
    return () => controller.abort();
  }, []);

  if (!status) return null;
  const label = status === "ready" ? "服务就绪" : "服务在线";
  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        asChild
        size="sm"
        tooltip={label}
        className="pointer-events-none"
      >
        <Content role="status" aria-label="服务状态">
          <CircleCheckIcon aria-hidden="true" />
          <Text as="span">{label}</Text>
        </Content>
      </SidebarMenuButton>
    </SidebarMenuItem>
  );
}

function DestinationGroup({
  label,
  navLabel,
  destinations,
  current,
}: {
  label: string;
  navLabel: string;
  destinations: Destination[];
  current: string | undefined;
}) {
  return (
    <SidebarGroup role="navigation" aria-label={navLabel}>
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {destinations.map(({ href, label: itemLabel, icon: Icon }) => (
            <SidebarMenuItem key={href}>
              <SidebarMenuButton
                asChild
                isActive={current === href}
                tooltip={itemLabel}
              >
                <Link
                  href={href}
                  aria-current={current === href ? "page" : undefined}
                >
                  <Icon aria-hidden="true" />
                  <Text as="span">{itemLabel}</Text>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

// md 及以上的站点侧栏。展开 / 折叠为图标栏由 SidebarProvider 记住。
export function BasicSidebar() {
  const { session, current, personalHref } = useNavigation();

  return (
    <Sidebar
      collapsible="icon"
      role="complementary"
      aria-label="站点侧边栏"
      className="print:hidden"
    >
      <SidebarHeader>
        <Content className="flex items-center justify-between gap-2 px-1 group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:px-0">
          <BrandLockup href="/" collapsible />
          <SidebarTrigger aria-label="展开或收起侧栏" />
        </Content>
      </SidebarHeader>
      <SidebarContent>
        <DestinationGroup
          label="阅读"
          navLabel="站点导航"
          destinations={readingDestinations}
          current={current}
        />
        {session ? (
          <DestinationGroup
            label="工作台"
            navLabel="工作台导航"
            destinations={workspaceDestinations}
            current={current}
          />
        ) : null}
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <SidebarMenuButton tooltip="更多" aria-label="更多导航">
                      <MoreHorizontalIcon aria-hidden="true" />
                      <Text as="span">更多</Text>
                    </SidebarMenuButton>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    side="right"
                    align="start"
                    className="w-48"
                    aria-label="更多导航"
                  >
                    <MoreMenuItems />
                  </DropdownMenuContent>
                </DropdownMenu>
              </SidebarMenuItem>
              <SidebarMenuItem className="pt-2">
                <Button
                  asChild
                  className="w-full group-data-[collapsible=icon]:size-8 group-data-[collapsible=icon]:p-0"
                >
                  <Link
                    href={personalHref}
                    aria-label={session ? "管理个人关注" : "定制我的关注"}
                  >
                    <PlusIcon aria-hidden="true" />
                    <Text
                      as="span"
                      className="group-data-[collapsible=icon]:hidden"
                    >
                      {session ? "管理个人关注" : "定制我的关注"}
                    </Text>
                  </Link>
                </Button>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <ServiceStatus />
        </SidebarMenu>
        <SidebarSeparator className="mx-0" />
        <Content className="flex items-center justify-between gap-2 group-data-[collapsible=icon]:flex-col">
          {session ? (
            <AccountMenu />
          ) : (
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="登录账户">
                  <Link href="/login">
                    <UserRoundIcon aria-hidden="true" />
                    <Text as="span">登录账户</Text>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          )}
          <ThemeToggle />
        </Content>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}

// md 以下的顶栏：品牌与搜索入口。
export function BasicMobileHeader() {
  return (
    <Content
      as="header"
      aria-label="移动站点导航"
      className="flex h-14 shrink-0 items-center justify-between gap-3 px-4 md:hidden print:hidden"
    >
      <BrandLockup href="/" />
      <Button asChild variant="ghost" size="icon-lg" className="size-11">
        <Link href="/discover?mode=all" aria-label="搜索资讯">
          <SearchIcon aria-hidden="true" />
        </Link>
      </Button>
    </Content>
  );
}

// md 以下的固定底部导航：首页、探索、收藏、工作台、更多。
export function BasicMobileNavigation() {
  const { current, personalHref } = useNavigation();
  const [home, explore, , starred] = readingDestinations;
  const items = [
    { ...home, label: "首页" },
    { ...explore, label: "探索" },
    { ...starred, label: "收藏" },
  ];

  return (
    <NavigationMenu
      viewport={false}
      aria-label="手机导航"
      className="bg-background fixed inset-x-0 bottom-0 z-30 h-16 w-full max-w-none border-t px-2 *:w-full md:hidden print:hidden"
    >
      <NavigationMenuList className="w-full justify-between gap-0">
        {items.map(({ href, label, icon: Icon }) => (
          <NavigationMenuItem key={href} className="flex-1">
            <NavigationMenuLink
              asChild
              active={current === href}
              className="h-16 flex-col justify-center gap-1 px-2"
            >
              <Link
                href={href}
                aria-current={current === href ? "page" : undefined}
              >
                <Icon aria-hidden="true" />
                <Text as="span" size="xs">
                  {label}
                </Text>
              </Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
        ))}
        <NavigationMenuItem className="flex-1">
          <NavigationMenuLink
            asChild
            active={current === "/workspace"}
            className="h-16 flex-col justify-center gap-1 px-2"
          >
            <Link
              href={personalHref}
              aria-label="个人工作台"
              aria-current={current === "/workspace" ? "page" : undefined}
            >
              <LayoutDashboardIcon aria-hidden="true" />
              <Text as="span" size="xs">
                工作台
              </Text>
            </Link>
          </NavigationMenuLink>
        </NavigationMenuItem>
        <NavigationMenuItem className="flex-1">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="h-16 w-full flex-col gap-1 px-2"
                aria-label="更多导航"
              >
                <MoreHorizontalIcon aria-hidden="true" />
                <Text as="span" size="xs">
                  更多
                </Text>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              side="top"
              align="end"
              className="w-56"
              aria-label="更多导航"
            >
              <MoreMenuItems mobile />
            </DropdownMenuContent>
          </DropdownMenu>
        </NavigationMenuItem>
      </NavigationMenuList>
    </NavigationMenu>
  );
}
