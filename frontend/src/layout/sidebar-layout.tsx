"use client";

import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import type { PanelImperativeHandle } from "react-resizable-panels";

import { Content } from "@/components/ui/content";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { useSidebar } from "@/components/ui/sidebar";
import { BasicSidebar } from "./basic-sidebar";

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
  const ready = useSyncExternalStore(
    subscribeHydration,
    getClientSnapshot,
    getServerSnapshot,
  );

  useEffect(() => {
    if (!ready || isMobile) return;
    if (!initialized.current) {
      initialized.current = true;
      setOpen(initial.open);
      group.current?.style.setProperty("--sidebar-width", `${initial.width}px`);
      panel.current?.resize(initial.open ? initial.width : COLLAPSED_WIDTH);
      return;
    }
    if (open) {
      if (panel.current?.isCollapsed()) panel.current.resize(width.current);
    } else {
      panel.current?.collapse();
    }
    savePreference(width.current, open);
  }, [open, ready, isMobile, initial, setOpen]);

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
        minSize={MIN_WIDTH}
        maxSize={MAX_WIDTH}
        collapsedSize={COLLAPSED_WIDTH}
        collapsible
        groupResizeBehavior="preserve-pixel-size"
        onResize={({ inPixels }) => {
          if (isMobile || inPixels <= 0) return;
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
        onDoubleClick={() => {
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
