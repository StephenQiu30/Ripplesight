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

import { BasicFooter } from "./basic-footer";
import { BasicMobileHeader, BasicMobileNavigation } from "./basic-sidebar";
import { SidebarLayout } from "./sidebar-layout";
import { PageContainer } from "./page-container";
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
  const isLogin = pathname === "/login";

  useEffect(() => {
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [pathname]);

  return (
    <ThemeProvider>
      <IdentitySessionProvider session={session}>
        <LayoutScrollContext.Provider value={mainRef}>
          <TooltipProvider>
            <SidebarProvider className="h-dvh min-h-0 overflow-hidden print:block print:h-auto print:overflow-visible">
              <Button
                asChild
                className="sr-only focus-within:not-sr-only focus-within:fixed focus-within:top-3 focus-within:left-5 focus-within:z-50"
              >
                <UI.TextLink href="#page-content">跳到正文</UI.TextLink>
              </Button>
              <ShellLayout isLogin={isLogin}>
                <SidebarInset
                  asChild
                  id="main-content"
                  tabIndex={-1}
                  data-login={isLogin || undefined}
                  className="min-h-0 min-w-0 overflow-clip pb-16 focus-visible:outline-none data-[login=true]:pb-0 md:pb-0 print:overflow-visible print:pb-0"
                >
                  <UI.Content
                    as={isLogin ? "div" : "main"}
                    className="flex min-h-0 flex-1 flex-col"
                  >
                    {isLogin ? null : <BasicMobileHeader />}
                    <PageContainer
                      scrollRef={mainRef}
                      edgeToEdge={isLogin}
                      footer={isLogin ? <BasicFooter /> : undefined}
                    >
                      {children}
                    </PageContainer>
                  </UI.Content>
                </SidebarInset>
              </ShellLayout>
              {isLogin ? null : <BasicMobileNavigation />}
            </SidebarProvider>
          </TooltipProvider>
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

function ShellLayout({
  isLogin,
  children,
}: {
  isLogin: boolean;
  children: ReactNode;
}) {
  return isLogin ? children : <SidebarLayout>{children}</SidebarLayout>;
}
