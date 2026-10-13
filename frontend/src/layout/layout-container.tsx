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
    <Container className={cn("page-layout w-full min-w-0", className)}>
      {children}
    </Container>
  );
}
