"use client";
import * as UI from "@/components/ui/content";

import { Button } from "@/components/ui/button";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";

import { usePathname } from "next/navigation";
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactNode,
  type RefObject,
} from "react";

import { BasicMobileHeader, BasicMobileNavigation } from "./basic-sidebar";
import { SidebarLayout } from "./sidebar-layout";
import { PageContainer } from "./page-container";
import { IdentitySessionProvider } from "@/components/auth/session-context";
import { LoginProvider } from "@/components/auth/login-context";
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
        <LoginProvider>
          <LayoutScrollContext.Provider value={mainRef}>
            <TooltipProvider>
              <SidebarProvider className="h-dvh min-h-0 overflow-hidden print:block print:h-auto print:overflow-visible">
                <Button
                  asChild
                  className="sr-only focus-within:not-sr-only focus-within:fixed focus-within:top-3 focus-within:left-5 focus-within:z-50"
                >
                  <UI.TextLink href="#page-content">跳到正文</UI.TextLink>
                </Button>
                <SidebarLayout>
                  <SidebarInset
                    asChild
                    id="main-content"
                    tabIndex={-1}
                    className="min-h-0 min-w-0 overflow-clip pb-16 focus-visible:outline-none data-[login=true]:pb-0 md:pb-0 print:overflow-visible print:pb-0"
                  >
                    <UI.Content
                      as="main"
                      className="flex min-h-0 flex-1 flex-col"
                    >
                      <BasicMobileHeader />
                      <PageContainer scrollRef={mainRef}>
                        {children}
                      </PageContainer>
                    </UI.Content>
                  </SidebarInset>
                </SidebarLayout>
                <BasicMobileNavigation />
              </SidebarProvider>
            </TooltipProvider>
            <Toaster
              position="top-right"
              closeButton
              duration={6000}
              containerAriaLabel="通知"
            />
          </LayoutScrollContext.Provider>
        </LoginProvider>
      </IdentitySessionProvider>
    </ThemeProvider>
  );
}
