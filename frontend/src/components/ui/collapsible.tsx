"use client";

import { Collapsible as CollapsiblePrimitive } from "radix-ui";
import {
  createContext,
  useContext,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { cn } from "@/lib/utils";
import { useDisclosureMotion } from "@/hooks/use-disclosure-motion";

const OpenContext = createContext(false);
const DESKTOP_QUERY = "(min-width: 1024px)";
function subscribeDesktop(onChange: () => void) {
  const query = window.matchMedia(DESKTOP_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function Collapsible({
  open: controlledOpen,
  defaultOpen = false,
  onOpenChange,
  ...props
}: React.ComponentProps<typeof CollapsiblePrimitive.Root>) {
  const [uncontrolledOpen, setOpen] = useState(defaultOpen);
  const open = controlledOpen ?? uncontrolledOpen;
  return (
    <OpenContext.Provider value={open}>
      <CollapsiblePrimitive.Root
        data-slot="collapsible"
        {...props}
        open={open}
        onOpenChange={(next) => {
          if (controlledOpen === undefined) setOpen(next);
          onOpenChange?.(next);
        }}
      />
    </OpenContext.Provider>
  );
}

function CollapsibleTrigger({
  ...props
}: React.ComponentProps<typeof CollapsiblePrimitive.CollapsibleTrigger>) {
  return (
    <CollapsiblePrimitive.CollapsibleTrigger
      data-slot="collapsible-trigger"
      {...props}
    />
  );
}

function CollapsibleContent({
  motion,
  ...props
}: React.ComponentProps<typeof CollapsiblePrimitive.CollapsibleContent> & {
  motion?: "height" | "below-lg";
}) {
  if (motion) return <MotionCollapsibleContent {...props} motion={motion} />;
  return (
    <CollapsiblePrimitive.CollapsibleContent
      data-slot="collapsible-content"
      {...props}
    />
  );
}

/** Preserve state and animate the official Radix disclosure without delaying its controls. */
function MotionCollapsibleContent({
  motion,
  className,
  children,
  ...props
}: React.ComponentProps<typeof CollapsiblePrimitive.CollapsibleContent> & {
  motion: "height" | "below-lg";
}) {
  const root = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const open = useContext(OpenContext);
  const desktopViewport = useSyncExternalStore(
    subscribeDesktop,
    () => window.matchMedia(DESKTOP_QUERY).matches,
    () => true,
  );
  const desktop = motion === "below-lg" && desktopViewport;
  useDisclosureMotion(root, open, desktop, undefined, body);
  return (
    <CollapsiblePrimitive.CollapsibleContent
      {...props}
      ref={root}
      forceMount
      data-slot="collapsible-content"
      data-motion={motion}
      className={cn("motion-collapsible", className)}
    >
      <div ref={body} data-motion-body="">
        {children}
      </div>
    </CollapsiblePrimitive.CollapsibleContent>
  );
}

export { Collapsible, CollapsibleTrigger, CollapsibleContent };
