import type { ReactNode } from "react";
import { Content } from "@/components/ui/content";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type ReadingLayoutProps = {
  title: string;
  children: ReactNode;
  aside: ReactNode;
};

// BasicLayout owns the main/scroll container and the global navigation.
// This layout arranges the reading feed and discovery sidebar.
export function ReadingLayout({ title, children, aside }: ReadingLayoutProps) {
  return (
    <Card
      data-reading-layout=""
      className="min-h-full overflow-visible rounded-none p-0"
    >
      <CardHeader className="sr-only">
        <CardTitle role="heading" aria-level={1}>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent
        data-reading-columns=""
        className="grid min-h-full grid-cols-1 items-start gap-6 px-0 lg:grid-cols-3 lg:gap-0"
      >
        <Content
          data-reading-feed=""
          className="min-h-full min-w-0 border-x lg:col-span-2"
        >
          {children}
        </Content>
        <Content
          as="aside"
          aria-label="发现更多"
          data-reading-aside=""
          className="min-w-0 px-4 pb-6 lg:pt-3 xl:px-6"
        >
          {aside}
        </Content>
      </CardContent>
    </Card>
  );
}
