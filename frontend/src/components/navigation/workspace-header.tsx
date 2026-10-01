import Link from "next/link";
import { ChevronDownIcon } from "lucide-react";

import { BrandLockup } from "@/components/brand/brand-lockup";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const destinations = [
  { key: "topics", href: "/events", label: "我的关注" },
  { key: "content", href: "/content", label: "相关内容" },
  { key: "hotlists", href: "/hotlists", label: "热榜" },
  { key: "sources", href: "/sources", label: "来源设置" },
  { key: "jobs", href: "/jobs", label: "采集记录" },
  { key: "reports", href: "/reports", label: "已有报告" },
] as const;

type WorkspaceHeaderProps = {
  current: (typeof destinations)[number]["key"];
};

export function WorkspaceHeader({ current }: WorkspaceHeaderProps) {
  return (
    <header className="mx-auto flex min-h-20 max-w-6xl items-center justify-between gap-4 px-5 sm:px-8">
      <BrandLockup href="/" compactOnMobile />
      <nav aria-label="工作区导航" className="flex items-center gap-2">
        <div className="hidden items-center gap-1 md:flex">
          {destinations.slice(0, 4).map((destination) => (
            <Button
              key={destination.key}
              asChild
              variant={current === destination.key ? "secondary" : "ghost"}
              size="navigation"
            >
              <Link
                href={destination.href}
                aria-current={current === destination.key ? "page" : undefined}
              >
                {destination.label}
              </Link>
            </Button>
          ))}
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="navigation">
              <span className="md:hidden">
                {
                  destinations.find(
                    (destination) => destination.key === current,
                  )?.label
                }
              </span>
              <span className="hidden md:inline">更多</span>
              <ChevronDownIcon data-icon="inline-end" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-44">
            <DropdownMenuGroup>
              {destinations.map((destination, index) => (
                <DropdownMenuItem
                  key={destination.key}
                  asChild
                  className={index < 4 ? "md:hidden" : undefined}
                >
                  <Link
                    href={destination.href}
                    aria-current={
                      current === destination.key ? "page" : undefined
                    }
                  >
                    {destination.label}
                  </Link>
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </nav>
    </header>
  );
}
