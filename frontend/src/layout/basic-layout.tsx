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
import { BasicSidebar } from "./basic-sidebar";
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
            <LayoutContainer className="flex min-h-0 flex-1 overflow-hidden px-0 sm:px-0 print:block print:overflow-visible">
              {pathname !== "/login" && <BasicSidebar />}
              <UI.Content
                as="main"
                id="main-content"
                ref={mainRef}
                tabIndex={-1}
                data-login={pathname === "/login" || undefined}
                className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-y-contain scroll-smooth pb-16 focus-visible:outline-none data-[login=true]:pb-0 motion-reduce:scroll-auto md:pb-0 print:overflow-visible"
              >
                <LayoutContainer
                  className={
                    pathname === "/"
                      ? "flex min-h-full flex-col px-0 py-0 sm:px-0 print:block"
                      : "flex min-h-full flex-col py-8 sm:py-10 print:block print:py-0"
                  }
                >
                  {children}
                </LayoutContainer>
                <BasicFooter />
              </UI.Content>
            </LayoutContainer>
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
