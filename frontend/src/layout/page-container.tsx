import type { ReactNode, Ref } from "react";

import { Content } from "@/components/ui/content";
import { cn } from "@/lib/utils";
import { LayoutContainer } from "./layout-container";

type PageContainerProps = {
  children: ReactNode;
  footer?: ReactNode;
  scrollRef?: Ref<HTMLElement>;
  edgeToEdge?: boolean;
};

/** Owns the viewport boundary; page content never shares flex sizing with the footer. */
export function PageContainer({
  children,
  footer,
  scrollRef,
  edgeToEdge = false,
}: PageContainerProps) {
  return (
    <Content
      data-page-container=""
      className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-clip print:block print:overflow-visible"
    >
      <Content
        id="page-content"
        ref={scrollRef}
        role="region"
        aria-label="页面内容"
        tabIndex={-1}
        className="layout-region hide-scrollbar relative min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-y-contain scroll-smooth focus-visible:outline-none motion-reduce:scroll-auto print:overflow-visible"
      >
        <LayoutContainer
          className={cn(
            "flex min-h-full flex-col pt-2 pb-10 md:pt-8 md:pb-16 print:block print:py-0",
            edgeToEdge &&
              "min-h-0 max-w-none px-0 py-0 md:px-0 md:py-0 lg:px-0",
          )}
        >
          {children}
        </LayoutContainer>
        {footer}
      </Content>
    </Content>
  );
}
