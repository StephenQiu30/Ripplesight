import type { ReactNode } from "react";
import { Content } from "@/components/ui/content";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type ReadingLayoutProps = {
  title: string;
  navigation: ReactNode;
  children: ReactNode;
  aside: ReactNode;
};

// BasicLayout owns the single main/scroll container. This layout only arranges
// reading content: desktop 20/50/30, mobile feed first and recommendations after.
export function ReadingLayout({
  title,
  navigation,
  children,
  aside,
}: ReadingLayoutProps) {
  return (
    <Card data-reading-layout="" className="overflow-visible p-0">
      <CardHeader className="sr-only">
        <CardTitle role="heading" aria-level={1}>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent
        data-reading-columns=""
        className="grid grid-cols-1 items-start gap-6 px-0 lg:grid-cols-[minmax(0,2fr)_minmax(0,5fr)_minmax(0,3fr)] xl:gap-8"
      >
        <Content
          as="aside"
          aria-label="阅读导航"
          data-reading-navigation=""
          className="hidden min-w-0 lg:sticky lg:top-4 lg:block"
        >
          {navigation}
        </Content>
        <Content data-reading-feed="" className="min-w-0">
          {children}
        </Content>
        <Content
          as="aside"
          aria-label="发现更多"
          data-reading-aside=""
          className="min-w-0 lg:sticky lg:top-4"
        >
          {aside}
        </Content>
      </CardContent>
    </Card>
  );
}
