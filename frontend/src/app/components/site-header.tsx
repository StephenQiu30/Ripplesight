import Link from "next/link";
import { BookOpenIcon, MenuIcon, PlusIcon } from "lucide-react";

import { BrandLockup } from "@/components/brand/brand-lockup";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

type SiteHeaderProps = {
  onGuide: (trigger: HTMLElement) => void;
};

export function SiteHeader({ onGuide }: SiteHeaderProps) {
  return (
    <header className="mx-auto flex h-20 w-full max-w-384 shrink-0 items-center px-5 sm:px-8 md:h-22 2xl:px-7">
      <BrandLockup href="/" compactOnMobile />
      <nav
        aria-label="主导航"
        className="ml-4 flex items-center gap-4 md:ml-10 md:gap-7 2xl:ml-12 2xl:gap-10"
      >
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="homeNavigation" aria-label="产品导航">
              <span className="hidden md:inline">产品</span>
              <MenuIcon data-icon="inline-start" className="md:hidden" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-44">
            <DropdownMenuGroup>
              <DropdownMenuItem asChild>
                <Link href="/monitors/new">
                  <PlusIcon />
                  创建关注
                </Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/events">我的关注</Link>
              </DropdownMenuItem>
              <DropdownMenuItem asChild>
                <Link href="/sources">来源设置</Link>
              </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button
          variant="ghost"
          size="homeNavigation"
          aria-label="使用指南"
          onClick={(event) => onGuide(event.currentTarget)}
        >
          <span className="hidden md:inline">使用指南</span>
          <BookOpenIcon data-icon="inline-start" className="md:hidden" />
        </Button>
      </nav>
      <Button asChild variant="outline" size="homeHeader" className="ml-auto">
        <Link href="/events">我的关注</Link>
      </Button>
    </header>
  );
}
