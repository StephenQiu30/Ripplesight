"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";
import { LocalReadingPreferences } from "@/components/publication/local-reading";

const entries = [
  ["/discover", "资讯"],
  ["/discover/topics", "行业专题"],
  ["/reports/daily", "日周月刊"],
  ["/discover/starred", "本机收藏"],
];

export function PublicationNavigation() {
  const pathname = usePathname();
  const current = entries
    .filter(([href]) => pathname === href || pathname?.startsWith(`${href}/`))
    .sort((a, b) => b[0].length - a[0].length)[0]?.[0];
  return (
    <NavigationMenu
      viewport={false}
      className="mb-8 max-w-full justify-start"
      aria-label="资讯阅读入口"
    >
      <NavigationMenuList className="flex-wrap justify-start gap-2">
        {entries.map(([href, label]) => (
          <NavigationMenuItem key={href}>
            <NavigationMenuLink asChild active={current === href}>
              <Link
                href={href}
                aria-current={current === href ? "page" : undefined}
              >
                {label}
              </Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
        ))}
        <NavigationMenuItem>
          <LocalReadingPreferences />
        </NavigationMenuItem>
      </NavigationMenuList>
    </NavigationMenu>
  );
}
