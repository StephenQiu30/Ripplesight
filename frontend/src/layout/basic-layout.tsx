"use client";
import * as UI from "@/components/ui/content";

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
import { ThemeProvider } from "./theme-toggle";

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
    <ThemeProvider>
      <IdentitySessionProvider session={session}>
        <LayoutScrollContext.Provider value={mainRef}>
          <UI.Content className="bg-background flex h-dvh flex-col overflow-hidden print:h-auto print:overflow-visible">
            <Button
              asChild
              className="sr-only focus-within:not-sr-only focus-within:fixed focus-within:top-3 focus-within:left-5 focus-within:z-50"
            >
              <UI.TextLink href="#main-content">跳到正文</UI.TextLink>
            </Button>
            {pathname !== "/login" && <BasicHeader />}
            <UI.Content
              as="main"
              id="main-content"
              ref={mainRef}
              tabIndex={-1}
              className="layout-region min-h-0 flex-1 overflow-y-auto overscroll-y-contain scroll-smooth focus-visible:outline-none motion-reduce:scroll-auto print:overflow-visible"
            >
              <LayoutContainer
                className={
                  pathname === "/"
                    ? "flex min-h-full flex-col py-4 sm:py-5 print:block print:py-0"
                    : "flex min-h-full flex-col py-10 sm:py-12 print:block print:py-0"
                }
              >
                {children}
              </LayoutContainer>
            </UI.Content>
            <BasicFooter />
          </UI.Content>
          <Toaster
            position="top-right"
            closeButton
            duration={6000}
            containerAriaLabel="通知"
          />
        </LayoutScrollContext.Provider>
      </IdentitySessionProvider>
    </ThemeProvider>
  );
}
