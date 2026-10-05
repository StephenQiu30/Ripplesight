import * as UI from "@/components/ui/content";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function LayoutContainer({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <UI.Content
      className={cn("mx-auto w-full max-w-7xl min-w-0 px-5 sm:px-8", className)}
    >
      {children}
    </UI.Content>
  );
}
