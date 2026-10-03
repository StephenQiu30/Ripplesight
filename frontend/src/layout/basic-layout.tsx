"use client";

import { usePathname } from "next/navigation";
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactNode,
  type RefObject,
} from "react";

import { BasicFooter } from "./basic-footer";
import { BasicHeader } from "./basic-header";
import { LayoutContainer } from "./layout-container";
import { IdentitySessionProvider } from "@/components/auth/session-context";
import { Toaster } from "@/components/ui/sonner";

const LayoutScrollContext = createContext<RefObject<HTMLElement | null> | null>(
  null,
);

export function useLayoutScrollContainer() {
  return useContext(LayoutScrollContext);
}

export function BasicLayout({
  children,
  session = null,
}: {
  children: ReactNode;
  session?: HotKeyAPI.IdentitySessionView | null;
}) {
  const pathname = usePathname();
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [pathname]);

  return (
    <IdentitySessionProvider session={session}>
      <LayoutScrollContext.Provider value={mainRef}>
        <div className="bg-background flex h-dvh flex-col overflow-hidden print:h-auto print:overflow-visible">
          <a
            href="#main-content"
            className="bg-background text-foreground sr-only rounded-md px-4 py-3 focus:not-sr-only focus:fixed focus:top-3 focus:left-5 focus:z-50"
          >
            跳到正文
          </a>
          {pathname !== "/login" && <BasicHeader />}
          <main
            id="main-content"
            ref={mainRef}
            tabIndex={-1}
            className="layout-region min-h-0 flex-1 overflow-y-auto overscroll-y-contain scroll-smooth focus-visible:outline-none motion-reduce:scroll-auto print:overflow-visible"
          >
            <LayoutContainer className="flex min-h-full flex-col py-10 sm:py-12 print:block print:py-0">
              {children}
            </LayoutContainer>
          </main>
          <BasicFooter />
        </div>
        <Toaster
          position="top-right"
          closeButton
          duration={6000}
          containerAriaLabel="通知"
        />
      </LayoutScrollContext.Provider>
    </IdentitySessionProvider>
  );
}
