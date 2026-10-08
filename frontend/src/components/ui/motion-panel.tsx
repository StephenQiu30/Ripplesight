"use client";

import { useRef } from "react";
import { Content } from "@/components/ui/content";
import { useDisclosureMotion } from "@/hooks/use-disclosure-motion";
import { cn } from "@/lib/utils";

/** Semantic panel for existing controls that share a separate button row. */
export function MotionPanel({
  open,
  triggerId,
  className,
  children,
  ...props
}: React.ComponentProps<typeof Content> & {
  open: boolean;
  triggerId: string;
}) {
  const root = useRef<HTMLElement>(null);
  const body = useRef<HTMLDivElement>(null);
  useDisclosureMotion(root, open, false, triggerId, body);
  return (
    <Content
      {...props}
      ref={root}
      role="region"
      data-slot="motion-panel"
      data-closed={!open || undefined}
      aria-hidden={!open || undefined}
      className={cn("motion-panel", className)}
    >
      <div ref={body} data-motion-body="">
        {children}
      </div>
    </Content>
  );
}
