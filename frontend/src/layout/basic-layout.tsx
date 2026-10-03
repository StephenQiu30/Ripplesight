"use client";
import { Button } from "@/components/ui/button";

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
          <Button
            asChild
            className="sr-only focus-within:not-sr-only focus-within:fixed focus-within:top-3 focus-within:left-5 focus-within:z-50"
          >
            <a href="#main-content">跳到正文</a>
          </Button>
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
