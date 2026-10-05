import * as UI from "@/components/ui/content";
import { Button } from "@/components/ui/button";
import Image from "next/image";
import Link from "next/link";

import { cn } from "@/lib/utils";

export function BrandMark() {
  return (
    <Image
      src="/icon.png?v=2"
      alt=""
      aria-hidden="true"
      width={44}
      height={44}
      loading="eager"
      unoptimized
      className="size-11 shrink-0 mix-blend-multiply dark:mix-blend-screen dark:invert"
    />
  );
}

type BrandLockupProps = {
  href: string;
  compactOnMobile?: boolean;
  showEnglish?: boolean;
};

export function BrandLockup({
  href,
  compactOnMobile = false,
  showEnglish = false,
}: BrandLockupProps) {
  return (
    <Button
      asChild
      variant="ghost"
      className="h-auto min-h-11 gap-3 px-0 hover:bg-transparent"
    >
      <Link
        href={href}
        aria-label={href === "/" ? "知微见澜首页" : "知微见澜工作台"}
      >
        <BrandMark />
        <UI.Text
          as="span"
          className={cn(
            "text-base font-semibold tracking-tight sm:text-lg",
            compactOnMobile && "hidden sm:inline",
          )}
        >
          知微见澜
        </UI.Text>
        {showEnglish ? (
          <UI.Text
            as="span"
            className="text-muted-foreground hidden text-sm sm:inline"
          >
            / Ripplesight
          </UI.Text>
        ) : null}
      </Link>
    </Button>
  );
}
