"use client";

import { Collapsible as CollapsiblePrimitive } from "radix-ui";
import {
  createContext,
  useContext,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { cn } from "@/lib/utils";
import { useReducedMotion } from "@/hooks/use-reduced-motion";

gsap.registerPlugin(useGSAP);
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
  motion?: "below-lg";
}) {
  if (motion) return <MotionCollapsibleContent {...props} />;
  return (
    <CollapsiblePrimitive.CollapsibleContent
      data-slot="collapsible-content"
      {...props}
    />
  );
}

/** Keep the topic list mounted while animating its Radix disclosure on narrow screens. */
function MotionCollapsibleContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof CollapsiblePrimitive.CollapsibleContent>) {
  const root = useRef<HTMLDivElement>(null);
  const open = useContext(OpenContext);
  const reducedMotion = useReducedMotion();
  const desktop = useSyncExternalStore(
    subscribeDesktop,
    () => window.matchMedia(DESKTOP_QUERY).matches,
    () => true,
  );
  const initialized = useRef(false);
  const tween = useRef<gsap.core.Tween | null>(null);
  const { contextSafe } = useGSAP({ scope: root });
  useGSAP(
    () => {
      const node = root.current;
      if (!node) return;
      const finish = contextSafe(() => {
        if (!open && !desktop) node.setAttribute("data-motion-hidden", "");
        gsap.set(node, { clearProps: "height,opacity,overflow" });
      });
      tween.current?.kill();
      const from = node.getBoundingClientRect().height;
      node.setAttribute("data-motion-mounted", "");
      node.removeAttribute("data-motion-hidden");
      node.inert = !open && !desktop;
      if (!open && !desktop) {
        node.setAttribute("aria-hidden", "true");
        if (node.contains(document.activeElement)) {
          node
            .closest('[data-slot="collapsible"]')
            ?.querySelector<HTMLElement>('[data-slot="collapsible-trigger"]')
            ?.focus();
        }
      } else node.removeAttribute("aria-hidden");
      if (!initialized.current || desktop || reducedMotion) {
        initialized.current = true;
        finish();
        return;
      }
      gsap.set(node, { height: from, overflow: "hidden" });
      tween.current = gsap.to(node, {
        height: open ? "auto" : 0,
        opacity: open ? 1 : 0,
        duration: 0.18,
        ease: "power2.out",
        onComplete: finish,
      });
    },
    { scope: root, dependencies: [open, desktop, reducedMotion] },
  );
  return (
    <CollapsiblePrimitive.CollapsibleContent
      {...props}
      ref={root}
      forceMount
      data-slot="collapsible-content"
      className={cn("motion-collapsible", className)}
    >
      {children}
    </CollapsiblePrimitive.CollapsibleContent>
  );
}

export { Collapsible, CollapsibleTrigger, CollapsibleContent };
