import type { ReactNode, Ref } from "react";

import { Content } from "@/components/ui/content";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { LayoutContainer } from "./layout-container";

type PageContainerProps = {
  children: ReactNode;
  header?: ReactNode;
  footer?: ReactNode;
  scrollRef?: Ref<HTMLElement>;
  edgeToEdge?: boolean;
};

/** Owns the viewport boundary; page content never shares flex sizing with the footer. */
export function PageContainer({
  children,
  header,
  footer,
  scrollRef,
  edgeToEdge = false,
}: PageContainerProps) {
  return (
    <Content
      data-page-container=""
      className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-clip print:block print:overflow-visible"
    >
      {header && (
        <Content
          as="header"
          aria-label="页面位置"
          className="shrink-0 print:hidden"
        >
          <LayoutContainer className="flex min-h-12 items-center py-2">
            {header}
          </LayoutContainer>
          <Separator />
        </Content>
      )}
      <Content
        id="page-content"
        ref={scrollRef}
        role="region"
        aria-label="页面内容"
        tabIndex={-1}
        className="layout-region relative min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-y-contain scroll-smooth focus-visible:outline-none motion-reduce:scroll-auto print:overflow-visible"
      >
        <LayoutContainer
          className={cn(
            "flex min-h-full flex-col py-6 sm:py-8 print:block print:py-0",
            edgeToEdge && "px-0 py-0 sm:px-0 sm:py-0",
          )}
        >
          {children}
        </LayoutContainer>
        {footer}
      </Content>
    </Content>
  );
}
