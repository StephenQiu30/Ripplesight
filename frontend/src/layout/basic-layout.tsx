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
import {
  BasicMobileHeader,
  BasicMobileNavigation,
  BasicSidebar,
} from "./basic-sidebar";
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
  sidebarOpen = true,
}: {
  children: ReactNode;
  session?: HotKeyAPI.IdentitySessionView | null;
  /** 侧栏上次是展开还是收起，由根布局从 cookie 读出，避免首屏闪动。 */
  sidebarOpen?: boolean;
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
            <SidebarProvider
              defaultOpen={sidebarOpen}
              className="h-dvh min-h-0 overflow-hidden print:block print:h-auto print:overflow-visible"
            >
              <Button
                asChild
                className="sr-only focus-within:not-sr-only focus-within:fixed focus-within:top-3 focus-within:left-5 focus-within:z-50"
              >
                <UI.TextLink href="#main-content">跳到正文</UI.TextLink>
              </Button>
              {isLogin ? null : <BasicSidebar />}
              <SidebarInset
                id="main-content"
                ref={mainRef}
                tabIndex={-1}
                data-login={isLogin || undefined}
                className="min-h-0 min-w-0 overflow-y-auto overscroll-y-contain scroll-smooth pb-16 focus-visible:outline-none data-[login=true]:pb-0 motion-reduce:scroll-auto md:pb-0 print:overflow-visible print:pb-0"
              >
                {isLogin ? null : <BasicMobileHeader />}
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
              </SidebarInset>
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
