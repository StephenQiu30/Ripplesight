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
      width={36}
      height={36}
      loading="eager"
      unoptimized
      className={cn(
        "size-9 shrink-0 mix-blend-multiply dark:mix-blend-screen dark:invert",
        className,
      )}
    />
  );
}

export function BrandLockup({
  href,
  compactOnMobile = false,
  rail = false,
  collapsible = false,
  bilingual = false,
}: {
  href: string;
  compactOnMobile?: boolean;
  rail?: boolean;
  collapsible?: boolean;
  bilingual?: boolean;
}) {
  return (
    <Button asChild variant="brand" size="brand">
      <Link
        href={href}
        aria-label={href === "/" ? "Ripplesight首页" : "Ripplesight工作台"}
      >
        <BrandMark
          className={cn(
            "size-6 md:size-9",
            collapsible && "group-data-[collapsible=icon]:size-8",
          )}
        />
        <UI.Content
          className={cn(
            "flex min-w-0 flex-col items-start gap-0",
            collapsible &&
              "overflow-hidden [&>span]:max-w-full [&>span]:truncate",
            compactOnMobile && "hidden sm:flex",
            rail && "hidden lg:flex",
            collapsible && "group-data-[collapsible=icon]:hidden",
          )}
        >
          <UI.Text as="strong" size="brand">
            {bilingual ? "知微见澜 / Ripplesight" : "知微见澜"}
          </UI.Text>
          {collapsible ? (
            <UI.Text as="span" tone="muted" size="xs">
              Ripplesight · AI 热点监测
            </UI.Text>
          ) : null}
        </UI.Content>
      </Link>
    </Button>
  );
}
