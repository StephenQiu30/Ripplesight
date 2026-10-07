import * as UI from "@/components/ui/content";
import { Button } from "@/components/ui/button";
import Image from "next/image";
import Link from "next/link";

import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <Image
      src="/icon.png?v=2"
      alt=""
      aria-hidden="true"
      width={44}
      height={44}
      loading="eager"
      unoptimized
      className={cn(
        "size-11 shrink-0 mix-blend-multiply dark:mix-blend-screen dark:invert",
        className,
      )}
    />
  );
}

type BrandLockupProps = {
  href: string;
  compactOnMobile?: boolean;
  rail?: boolean;
  /** 放在可折叠侧栏里：折叠为图标栏时只保留标识。 */
  collapsible?: boolean;
};

export function BrandLockup({
  href,
  compactOnMobile = false,
  rail = false,
  collapsible = false,
}: BrandLockupProps) {
  return (
    <Button
      asChild
      variant="ghost"
      className={cn(
        "h-auto min-h-11 gap-3 px-0 hover:bg-transparent",
        collapsible && "group-data-[collapsible=icon]:min-h-8",
      )}
    >
      <Link
        href={href}
        aria-label={href === "/" ? "Ripplesight首页" : "Ripplesight工作台"}
      >
        <BrandMark
          className={
            collapsible ? "group-data-[collapsible=icon]:size-8" : undefined
          }
        />
        <UI.Text
          as="span"
          className={cn(
            "text-base font-semibold tracking-tight sm:text-lg",
            compactOnMobile && "hidden sm:inline",
            rail && "hidden lg:inline",
            collapsible && "group-data-[collapsible=icon]:hidden",
          )}
        >
          Ripplesight
        </UI.Text>
      </Link>
    </Button>
  );
}
