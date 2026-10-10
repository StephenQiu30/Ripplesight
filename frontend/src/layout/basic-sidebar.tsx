"use client";

import { AuthLink as Link } from "@/components/auth/auth-link";
import { usePathname } from "next/navigation";

import {
  BellRingIcon,
  InfoIcon,
  MessageSquareIcon,
  LogInIcon,
  SettingsIcon,
  BookmarkIcon,
  ActivityIcon,
  EyeIcon,
  Settings2Icon,
  PlugIcon,
  ChartNoAxesColumnIcon,
  CompassIcon,
  FileTextIcon,
  HomeIcon,
  LayoutDashboardIcon,
  MoreHorizontalIcon,
  SearchIcon,
  UserRoundIcon,
  type LucideIcon,
} from "lucide-react";

import { AccountMenu } from "@/components/auth/account-menu";
import { useIdentitySession } from "@/components/auth/session-context";
import { BrandLockup } from "@/components/brand/brand-lockup";
import { Button } from "@/components/ui/button";
import { Content, Text } from "@/components/ui/content";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuSeparator,
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
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import { MenuNavigation } from "@/components/navigation/menu-navigation";
import { ThemeMenuItems } from "./theme-toggle";

type Destination = {
  href: string;
  label: string;
  icon: LucideIcon;
  match: string[];
};

const readingDestinations: Destination[] = [
  { href: "/", label: "今日热点", icon: HomeIcon, match: ["/"] },
  {
    href: "/discover?mode=all",
    label: "探索",
    icon: CompassIcon,
    match: ["/discover", "/items"],
  },
  {
    href: "/discover/stories",
    label: "事件",
    icon: ActivityIcon,
    match: ["/discover/stories", "/events"],
  },
  {
    href: "/leaderboard",
    label: "榜单",
    icon: ChartNoAxesColumnIcon,
    match: ["/leaderboard"],
  },
  {
    href: "/reports/daily",
    label: "日报",
    icon: FileTextIcon,
    match: [
      "/reports/daily",
      "/reports/weekly",
      "/reports/monthly",
      "/editions",
    ],
  },
];
const starredDestination: Destination = {
  href: "/discover/starred",
  label: "收藏",
  icon: BookmarkIcon,
  match: ["/discover/starred"],
};
const workspaceDestinations: Destination[] = [
  {
    href: "/monitors/new",
    label: "设置关键词",
    icon: Settings2Icon,
    match: ["/monitors/new"],
  },
  { href: "/sources", label: "平台接入", icon: PlugIcon, match: ["/sources"] },
  {
    href: "/topics",
    label: "监控主题",
    icon: EyeIcon,
    match: ["/topics", "/monitors"],
  },
  { href: "/alerts", label: "告警", icon: BellRingIcon, match: ["/alerts"] },
  starredDestination,
];
const moreDestinations: Destination[] = [
  {
    href: "/workspace",
    label: "工作台",
    icon: LayoutDashboardIcon,
    match: [
      "/workspace",
      "/jobs",
      "/content",
      "/sources",
      "/operations",
      "/publication",
      "/sources/editorial",
      "/feeds",
      "/hotlists",
      "/account",
      "/site",
      "/agent",
    ],
  },
  {
    href: "/reports",
    label: "我的报告",
    icon: FileTextIcon,
    match: ["/reports"],
  },
  {
    href: "/discover/topics",
    label: "专题",
    icon: CompassIcon,
    match: ["/discover/topics"],
  },
];

function useNavigation() {
  const pathname = usePathname() ?? "/";
  const session = useIdentitySession();
  const destinations = [
    ...readingDestinations,
    ...workspaceDestinations,
    ...moreDestinations,
  ];
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
  const { session, destinations, current } = useNavigation();
  return (
    <>
      <MenuNavigation
        label={mobile ? "站点导航" : "更多探索"}
        items={(mobile ? destinations : moreDestinations).filter(
          ({ href }) => href !== "/",
        )}
        current={current}
      />
      <DropdownMenuSeparator />
      <MenuNavigation
        label={session && !mobile ? "帮助与反馈" : "帮助与账户"}
        items={[
          { href: "/about", label: "关于 Ripplesight", icon: InfoIcon },
          { href: "/feedback", label: "意见反馈", icon: MessageSquareIcon },
          ...(!session || mobile
            ? [
                {
                  href: session ? "/account" : "/login",
                  label: session ? "账户设置" : "登录",
                  icon: session ? SettingsIcon : LogInIcon,
                },
              ]
            : []),
        ]}
      />
      <DropdownMenuSeparator />
      <ThemeMenuItems />
    </>
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
    <SidebarGroup
      role="navigation"
      aria-label={navLabel}
      className="px-3 pt-0 pb-4 group-data-[collapsible=icon]:px-2"
    >
      <SidebarGroupLabel className="h-7 group-data-[collapsible=icon]:hidden">
        {label}
      </SidebarGroupLabel>
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
  const { session, current } = useNavigation();
  const { open } = useSidebar();

  return (
    <Sidebar
      collapsible="icon"
      role="complementary"
      aria-label="站点侧边栏"
      className="hidden shrink-0 transition-none md:flex print:hidden"
    >
      <SidebarHeader className="h-22 flex-row items-center justify-between gap-1 px-3 group-data-[collapsible=icon]:h-auto group-data-[collapsible=icon]:flex-col group-data-[collapsible=icon]:px-2 group-data-[collapsible=icon]:py-4">
        <BrandLockup href="/" collapsible />
        <SidebarTrigger
          aria-label={open ? "折叠侧边栏" : "展开侧边栏"}
          title={open ? "折叠侧边栏" : "展开侧边栏"}
          aria-expanded={open}
        />
      </SidebarHeader>
      <SidebarContent>
        <DestinationGroup
          label="阅读"
          navLabel="站点导航"
          destinations={readingDestinations}
          current={current}
        />
        <DestinationGroup
          label="工作台"
          navLabel="工作台导航"
          destinations={workspaceDestinations}
          current={current}
        />
      </SidebarContent>
      <SidebarFooter className="gap-3 px-3 py-3 group-data-[collapsible=icon]:px-2">
        <Content className="flex items-center justify-between gap-1 group-data-[collapsible=icon]:flex-col">
          {session ? (
            <AccountMenu />
          ) : (
            <Button asChild variant="ghost" size="sm">
              <Link href="/login" aria-label="登录账户">
                <UserRoundIcon data-icon="inline-start" />
                <Text
                  as="span"
                  className="group-data-[collapsible=icon]:hidden"
                >
                  登录账户
                </Text>
              </Link>
            </Button>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="更多导航"
                title="更多导航与外观"
              >
                <MoreHorizontalIcon data-icon="inline-start" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              side="top"
              align="start"
              variant="navigation"
              sideOffset={8}
              collisionPadding={16}
              aria-label="更多导航"
            >
              <MoreMenuItems />
            </DropdownMenuContent>
          </DropdownMenu>
        </Content>
      </SidebarFooter>
    </Sidebar>
  );
}

// md 以下的顶栏：品牌与搜索入口。
export function BasicMobileHeader() {
  const session = useIdentitySession();
  return (
    <Content
      role="navigation"
      aria-label="移动站点导航"
      className="flex h-14 shrink-0 items-center justify-between gap-3 px-4 md:hidden print:hidden"
    >
      <BrandLockup href="/" />
      <Content className="flex items-center gap-1">
        <Button asChild variant="ghost" size="icon-lg" className="size-11">
          <Link href="/discover?mode=all" aria-label="搜索资讯">
            <SearchIcon aria-hidden="true" data-icon="inline-start" />
          </Link>
        </Button>
        <Button asChild variant="ghost" size="icon-lg">
          <Link href="/alerts" aria-label="告警">
            <BellRingIcon data-icon="inline-start" />
          </Link>
        </Button>
        {session && <AccountMenu compact />}
      </Content>
    </Content>
  );
}

// md 以下的固定底部导航：首页、探索、收藏、工作台、更多。
export function BasicMobileNavigation() {
  const { current } = useNavigation();
  const [home, explore] = readingDestinations;
  const items = [
    { ...home, label: "首页" },
    { ...explore, label: "探索" },
    { ...starredDestination, label: "收藏" },
  ];

  return (
    <NavigationMenu
      viewport={false}
      aria-label="手机导航"
      className="bg-sidebar fixed inset-x-0 bottom-0 z-30 h-16 w-full max-w-none px-2 *:w-full md:hidden print:hidden"
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
            active={current === "/topics"}
            className="h-16 flex-col justify-center gap-1 px-2"
          >
            <Link
              href="/topics"
              aria-label="监控主题"
              aria-current={current === "/topics" ? "page" : undefined}
            >
              <EyeIcon aria-hidden="true" />
              <Text as="span" size="xs">
                监控
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
                <MoreHorizontalIcon
                  aria-hidden="true"
                  data-icon="inline-start"
                />
                <Text as="span" size="xs">
                  更多
                </Text>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              side="top"
              align="end"
              variant="navigation"
              sideOffset={8}
              collisionPadding={16}
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
