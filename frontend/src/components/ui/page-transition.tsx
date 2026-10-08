"use client";

import { useRef } from "react";
import { usePathname } from "next/navigation";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

import { Content } from "@/components/ui/content";
import { useReducedMotion } from "@/hooks/use-reduced-motion";

gsap.registerPlugin(useGSAP);

/** Enter the new route immediately; never remount children or wait for an exit. */
export function PageTransition(props: React.ComponentProps<typeof Content>) {
  const root = useRef<HTMLElement>(null);
  const pathname = usePathname();
  const reducedMotion = useReducedMotion();
  useGSAP(
    () => {
      const node = root.current;
      if (!node || reducedMotion || node.contains(document.activeElement))
        return;
      gsap.fromTo(
        node,
        { opacity: 0.94, y: 4 },
        {
          opacity: 1,
          y: 0,
          duration: 0.18,
          ease: "power2.out",
          clearProps: "opacity,transform",
        },
      );
    },
    {
      scope: root,
      dependencies: [pathname, reducedMotion],
      revertOnUpdate: true,
    },
  );
  return <Content {...props} ref={root} data-slot="page-transition" />;
}
