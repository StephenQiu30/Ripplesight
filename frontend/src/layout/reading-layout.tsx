import type { ReactNode } from "react";
import { Content } from "@/components/ui/content";

/** Keeps the feed fluid and stacks supplementary content when space is limited. */
export function ReadingLayout({
  children,
  aside,
}: {
  children: ReactNode;
  aside: ReactNode;
}) {
  return (
    <Content
      data-reading-layout=""
      data-reading-columns=""
      className="reading-columns min-w-0 items-start"
    >
      <Content data-reading-feed="" className="min-w-0">
        {children}
      </Content>
      <Content
        as="aside"
        aria-label="发现更多"
        data-reading-aside=""
        className="min-w-0"
      >
        {aside}
      </Content>
    </Content>
  );
}
