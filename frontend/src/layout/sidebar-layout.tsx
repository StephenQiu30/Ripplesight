"use client";

import { useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import type { PanelImperativeHandle } from "react-resizable-panels";

import { Content } from "@/components/ui/content";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { useSidebar } from "@/components/ui/sidebar";
import { BasicSidebar } from "./basic-sidebar";
import { useReducedMotion } from "@/hooks/use-reduced-motion";

gsap.registerPlugin(useGSAP);

const STORAGE_KEY = "ripplesight-sidebar";
const DEFAULT_WIDTH = 240;
const MIN_WIDTH = 224;
const MAX_WIDTH = 320;
const COLLAPSED_WIDTH = 48;

const subscribeHydration = () => () => {};
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

function readPreference() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    if (
      saved &&
      typeof saved.width === "number" &&
      Number.isFinite(saved.width)
    ) {
      return {
        width: Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, saved.width)),
        open: typeof saved.open === "boolean" ? saved.open : true,
      };
    }
  } catch {
    // A missing or blocked preference store must not prevent navigation.
  }
  return { width: DEFAULT_WIDTH, open: true };
}

function savePreference(width: number, open: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ width, open }));
  } catch {
    // Preferences are optional; resizing remains usable for this visit.
  }
}

export function SidebarLayout({ children }: { children: ReactNode }) {
  const { open, setOpen, isMobile } = useSidebar();
  const panel = useRef<PanelImperativeHandle | null>(null);
  const group = useRef<HTMLDivElement | null>(null);
  const [initial] = useState(readPreference);
  const width = useRef(initial.width);
  const initialized = useRef(false);
  const animation = useRef<gsap.core.Tween | null>(null);
  const moving = useRef(false);
  const interacting = useRef(false);
  const [continuousSize, setContinuousSize] = useState(false);
  const reducedMotion = useReducedMotion();
  const ready = useSyncExternalStore(
    subscribeHydration,
    getClientSnapshot,
    getServerSnapshot,
  );

  const { contextSafe } = useGSAP({ scope: group });
  const killMotion = () => {
    animation.current?.kill();
    animation.current = null;
  };
  const finishMotion = () => {
    killMotion();
    moving.current = false;
    interacting.current = false;
    setContinuousSize(false);
  };
  const takeOverMotion = () => {
    if (!moving.current) return;
    killMotion();
    // Keep continuous constraints while the pointer/key owns the current size.
    // Tightening them here would snap a partial collapse before the drag starts.
    interacting.current = true;
  };

  useGSAP(
    () => {
      if (!ready) return;
      if (isMobile) {
        finishMotion();
        return;
      }
      if (!initialized.current) {
        initialized.current = true;
        setOpen(initial.open);
        group.current?.style.setProperty(
          "--sidebar-width",
          `${initial.width}px`,
        );
        panel.current?.resize(initial.open ? initial.width : COLLAPSED_WIDTH);
        return;
      }
      const target = open ? width.current : COLLAPSED_WIDTH;
      const from = panel.current?.getSize().inPixels ?? target;
      killMotion();
      interacting.current = false;
      moving.current = true;
      savePreference(width.current, open);
      if (reducedMotion || Math.abs(from - target) < 1) {
        panel.current?.resize(target);
        finishMotion();
        return;
      }
      // Relax the collapse gap only during motion. Each GSAP frame updates the
      // official panel layout, so a new drag sees the same size as the browser.
      setContinuousSize(true);
      const size = { width: from };
      animation.current = gsap.to(size, {
        width: target,
        duration: 0.22,
        ease: "power2.out",
        onUpdate: () => panel.current?.resize(size.width),
        onComplete: contextSafe(finishMotion),
      });
    },
    {
      scope: group,
      dependencies: [open, ready, isMobile, reducedMotion, initial, setOpen],
    },
  );

  useGSAP(
    () => {
      const release = contextSafe(() => {
        if (!interacting.current) return;
        const current = panel.current?.getSize().inPixels ?? COLLAPSED_WIDTH;
        const expanded = current >= (MIN_WIDTH + COLLAPSED_WIDTH) / 2;
        if (expanded)
          width.current = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, current));
        panel.current?.resize(expanded ? width.current : COLLAPSED_WIDTH);
        savePreference(width.current, expanded);
        finishMotion();
        setOpen(expanded);
      });
      window.addEventListener("pointerup", release);
      window.addEventListener("pointercancel", release);
      window.addEventListener("keyup", release);
      window.addEventListener("blur", release);
      return () => {
        window.removeEventListener("pointerup", release);
        window.removeEventListener("pointercancel", release);
        window.removeEventListener("keyup", release);
        window.removeEventListener("blur", release);
        killMotion();
      };
    },
    { scope: group },
  );

  // The third-party resize primitives need client-side styles under production
  // CSP. Keep the complete reading shell in SSR with the same default geometry.
  if (!ready) {
    return (
      <Content className="flex min-h-0 min-w-0 flex-1 print:block">
        <BasicSidebar />
        {children}
      </Content>
    );
  }

  return (
    <ResizablePanelGroup
      id="site-layout"
      elementRef={group}
      orientation="horizontal"
      disabled={isMobile}
      disableCursor
      className="site-resizable-layout min-h-0 min-w-0 flex-1"
    >
      <ResizablePanel
        id="site-navigation"
        panelRef={panel}
        defaultSize={initial.open ? initial.width : COLLAPSED_WIDTH}
        minSize={continuousSize ? COLLAPSED_WIDTH : MIN_WIDTH}
        maxSize={MAX_WIDTH}
        collapsedSize={COLLAPSED_WIDTH}
        collapsible
        groupResizeBehavior="preserve-pixel-size"
        onResize={({ inPixels }) => {
          if (isMobile || moving.current || inPixels <= 0) return;
          const expanded = inPixels > COLLAPSED_WIDTH + 1;
          if (expanded) {
            width.current = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, inPixels));
            group.current?.style.setProperty(
              "--sidebar-width",
              `${width.current}px`,
            );
          }
          savePreference(width.current, expanded);
          if (expanded !== open) setOpen(expanded);
        }}
      >
        <BasicSidebar />
      </ResizablePanel>
      <ResizableHandle
        aria-label="调整侧边栏宽度"
        title="拖动或使用方向键调整宽度，双击恢复默认宽度"
        disableDoubleClick
        onPointerDown={takeOverMotion}
        onKeyDown={takeOverMotion}
        onDoubleClick={() => {
          finishMotion();
          width.current = DEFAULT_WIDTH;
          panel.current?.resize(DEFAULT_WIDTH);
        }}
        className="z-20 hidden shrink-0 cursor-col-resize md:flex print:hidden"
      />
      <ResizablePanel id="site-content" minSize="0%">
        {children}
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
