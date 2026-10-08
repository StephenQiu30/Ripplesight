"use client";

import { useRef, type RefObject } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useReducedMotion } from "@/hooks/use-reduced-motion";

gsap.registerPlugin(useGSAP);

/** Keep disclosure content mounted, with focus and visibility tied to its state. */
export function useDisclosureMotion(
  root: RefObject<HTMLElement | null>,
  open: boolean,
  alwaysVisible = false,
  triggerId?: string,
  body?: RefObject<HTMLElement | null>,
) {
  const reducedMotion = useReducedMotion();
  const initialized = useRef(false);
  const tween = useRef<gsap.core.Tween | null>(null);
  const { contextSafe } = useGSAP({ scope: root });
  useGSAP(
    () => {
      const node = root.current;
      if (!node) return;
      const visible = open || alwaysVisible;
      const finish = contextSafe(() => {
        if (!visible) node.setAttribute("data-motion-hidden", "");
        gsap.set(node, { clearProps: "height,opacity,overflow" });
      });
      tween.current?.kill();
      const from = node.getBoundingClientRect().height;
      const opacity = from === 0 ? 0 : Number(getComputedStyle(node).opacity);
      node.setAttribute("data-motion-mounted", "");
      node.removeAttribute("data-motion-hidden");
      if (!visible) {
        node.setAttribute("aria-hidden", "true");
        if (node.contains(document.activeElement)) {
          const trigger = triggerId
            ? document.getElementById(triggerId)
            : node
                .closest('[data-slot="collapsible"]')
                ?.querySelector<HTMLElement>(
                  '[data-slot="collapsible-trigger"]',
                );
          trigger?.focus();
        }
      } else node.removeAttribute("aria-hidden");
      node.toggleAttribute("inert", !visible);
      if (!initialized.current || alwaysVisible || reducedMotion) {
        initialized.current = true;
        finish();
        return;
      }
      gsap.set(node, { height: from, opacity, overflow: "hidden" });
      const progress = { value: 0 };
      tween.current = gsap.to(progress, {
        value: 1,
        duration: 0.18,
        ease: "power2.out",
        onUpdate: () => {
          const target = visible
            ? (body?.current?.getBoundingClientRect().height ??
              node.scrollHeight)
            : 0;
          node.style.setProperty(
            "height",
            `${from + (target - from) * progress.value}px`,
          );
          node.style.setProperty(
            "opacity",
            String(opacity + ((visible ? 1 : 0) - opacity) * progress.value),
          );
        },
        onComplete: finish,
      });
    },
    {
      scope: root,
      dependencies: [open, alwaysVisible, reducedMotion, triggerId, body],
    },
  );
}
