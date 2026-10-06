import type { ReactNode } from "react";
import { Content, Heading } from "@/components/ui/content";
import { Separator } from "@/components/ui/separator";

type ReadingLayoutProps = {
  title: string;
  children: ReactNode;
  aside: ReactNode;
};

// BasicLayout owns the main/scroll container and the global navigation.
// This layout arranges the reading feed and discovery sidebar.
export function ReadingLayout({ title, children, aside }: ReadingLayoutProps) {
  return (
    <Content data-reading-layout="" className="min-h-full">
      <Heading level={1} className="sr-only">
        {title}
      </Heading>
      <Content
        data-reading-columns=""
        className="grid min-h-full grid-cols-1 items-start lg:grid-cols-3"
      >
        <Content
          data-reading-feed=""
          className="min-h-full min-w-0 lg:col-span-2"
        >
          {children}
        </Content>
        <Content
          as="aside"
          aria-label="发现更多"
          data-reading-aside=""
          className="relative min-w-0 self-stretch px-5 py-6 sm:px-8"
        >
          <Separator className="absolute inset-x-0 top-0 lg:hidden" />
          <Separator
            orientation="vertical"
            className="absolute inset-y-0 left-0 hidden lg:block"
          />
          {aside}
        </Content>
      </Content>
    </Content>
  );
}
