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
      className={cn(
        "mx-auto w-full max-w-screen-2xl min-w-0 px-4 md:px-8 lg:px-12",
        className,
      )}
    >
      {children}
    </UI.Content>
  );
}
