"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CheckIcon, MenuIcon } from "lucide-react";

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
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LayoutContainer } from "./layout-container";
import { ThemeToggle } from "./theme-toggle";

const readingDestinations = [
  { href: "/discover", label: "资讯" },
  { href: "/discover/topics", label: "专题" },
  { href: "/leaderboard", label: "模型榜" },
];

export function BasicHeader() {
  const pathname = usePathname();
  const session = useIdentitySession();
  const current = readingDestinations
    .filter(({ href }) => pathname === href || pathname?.startsWith(`${href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0];
  const workspace = !!session && !isPublicPagePath(pathname);
  const destinations = session
    ? [...readingDestinations, { href: "/workspace", label: "工作台" }]
    : readingDestinations;

  function active(href: string) {
    return href === "/workspace" ? workspace : current?.href === href;
  }

  return (
    <header className="layout-region bg-background shrink-0 overflow-hidden print:hidden">
      <LayoutContainer className="flex h-20 items-center justify-between gap-4">
        <BrandLockup href="/" compactOnMobile />
        <NavigationMenu
          viewport={false}
          aria-label="站点导航"
          className="min-w-0 flex-none"
        >
          <NavigationMenuList className="gap-1 sm:gap-2">
            {destinations.map((destination) => (
              <NavigationMenuItem
                key={destination.href}
                className="hidden md:block"
              >
                <NavigationMenuLink asChild active={active(destination.href)}>
                  <Link
                    href={destination.href}
                    aria-current={active(destination.href) ? "page" : undefined}
                  >
                    {destination.label}
                  </Link>
                </NavigationMenuLink>
              </NavigationMenuItem>
            ))}
            <NavigationMenuItem className="md:hidden">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="navigation"
                    aria-label="阅读导航"
                  >
                    <MenuIcon data-icon="inline-start" />
                    菜单
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="end"
                  className="w-48"
                  aria-label="阅读导航"
                >
                  <DropdownMenuGroup>
                    {destinations.map((destination) => (
                      <DropdownMenuItem
                        key={destination.href}
                        asChild
                        className="min-h-11 justify-between"
                      >
                        <Link
                          href={destination.href}
                          aria-current={
                            active(destination.href) ? "page" : undefined
                          }
                        >
                          {destination.label}
                          {active(destination.href) ? (
                            <CheckIcon aria-hidden="true" />
                          ) : null}
                        </Link>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuGroup>
                </DropdownMenuContent>
              </DropdownMenu>
            </NavigationMenuItem>
            <NavigationMenuItem>
              <ThemeToggle />
            </NavigationMenuItem>
            <NavigationMenuItem>
              {session ? (
                <AccountMenu />
              ) : (
                <Button asChild size="navigation">
                  <Link href="/login">登录</Link>
                </Button>
              )}
            </NavigationMenuItem>
          </NavigationMenuList>
        </NavigationMenu>
      </LayoutContainer>
    </header>
  );
}
