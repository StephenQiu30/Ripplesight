import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";
import Link from "next/link";
import type { ReactNode } from "react";

export default function LeaderboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <>
      <NavigationMenu
        viewport={false}
        className="mb-8 max-w-full justify-start"
        aria-label="模型榜阅读入口"
      >
        <NavigationMenuList className="flex-wrap justify-start gap-2">
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href="/leaderboard">模型榜</Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href="/leaderboard/sources">评测来源</Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href="/leaderboard/rules">计算规则</Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
        </NavigationMenuList>
      </NavigationMenu>
      {children}
    </>
  );
}
