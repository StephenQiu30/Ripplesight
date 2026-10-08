import * as UI from "@/components/ui/content";
import type { ReactNode } from "react";
import { PageTransition } from "@/components/ui/page-transition";

import { cn } from "@/lib/utils";

export function LayoutContainer({
  children,
  className,
  routeTransition = false,
}: {
  children: ReactNode;
  className?: string;
  routeTransition?: boolean;
}) {
  const Container = routeTransition ? PageTransition : UI.Content;
  return (
    <Container
      className={cn(
        "mx-auto w-full max-w-screen-2xl min-w-0 px-4 md:px-8 lg:px-12",
        className,
      )}
    >
      {children}
    </Container>
  );
}
