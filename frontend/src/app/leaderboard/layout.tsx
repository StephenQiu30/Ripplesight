import Link from "next/link";
import type { ReactNode } from "react";
import { BookOpenIcon, DatabaseIcon, ListOrderedIcon } from "lucide-react";

import * as UI from "@/components/ui/content";
import { Item, ItemContent, ItemTitle } from "@/components/ui/item";
import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";
import { Separator } from "@/components/ui/separator";

const readingLinks = [
  {
    href: "/leaderboard",
    title: "模型榜",
    description: "阅读已发布的模型排名",
    icon: ListOrderedIcon,
  },
  {
    href: "/leaderboard/sources",
    title: "评测来源",
    description: "核对来源覆盖与原始成绩",
    icon: DatabaseIcon,
  },
  {
    href: "/leaderboard/rules",
    title: "计算规则",
    description: "了解固定预算与证据边界",
    icon: BookOpenIcon,
  },
];

export default function LeaderboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <UI.Content className="flex min-w-0 flex-col gap-12">
      <UI.Content className="min-w-0">{children}</UI.Content>
      <UI.Content
        as="aside"
        aria-label="模型榜阅读入口"
        className="flex min-w-0 flex-col gap-4 border-t pt-6"
      >
        <UI.Heading level={2} appearance="sidebar">
          来源与规则
        </UI.Heading>
        <NavigationMenu
          viewport={false}
          className="max-w-full justify-start"
          aria-label="模型榜相关页面"
        >
          <NavigationMenuList className="w-full flex-wrap items-start">
            {readingLinks.map(({ href, title, description, icon: Icon }) => (
              <NavigationMenuItem key={href}>
                <NavigationMenuLink asChild>
                  <Link href={href}>
                    <UI.Content className="flex items-start gap-3">
                      <Icon aria-hidden="true" className="size-4 shrink-0" />
                      <UI.Content className="flex min-w-0 flex-col gap-1">
                        <UI.Text size="sm">{title}</UI.Text>
                        <UI.Text tone="muted" size="xs">
                          {description}
                        </UI.Text>
                      </UI.Content>
                    </UI.Content>
                  </Link>
                </NavigationMenuLink>
              </NavigationMenuItem>
            ))}
          </NavigationMenuList>
        </NavigationMenu>
        <Separator />
        <Item variant="muted">
          <ItemContent className="gap-3">
            <ItemTitle>怎样读榜</ItemTitle>
            <UI.Text tone="muted" size="sm">
              先看排名，再核对独立证据和稳定性。支持指数不代表能力差距或获胜概率。
            </UI.Text>
          </ItemContent>
        </Item>
      </UI.Content>
    </UI.Content>
  );
}
