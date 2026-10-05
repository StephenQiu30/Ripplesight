"use client";
import * as UI from "@/components/ui/content";

import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";

import Link from "next/link";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { LayoutContainer } from "./layout-container";
import { UsageGuide } from "./usage-guide";

export function BasicFooter() {
  const [guideOpen, setGuideOpen] = useState(false);
  const guideTriggerRef = useRef<HTMLButtonElement>(null);

  return (
    <>
      <UI.Content
        as="footer"
        role="contentinfo"
        className="layout-region bg-background shrink-0 overflow-hidden print:hidden"
      >
        <LayoutContainer className="text-muted-foreground flex min-h-16 flex-wrap items-center justify-between gap-x-6 gap-y-2 py-3 text-xs">
          <UI.Text>知微见澜 · Ripplesight</UI.Text>
          <NavigationMenu
            viewport={false}
            className="max-w-full justify-start"
            aria-label="站点信息"
          >
            <NavigationMenuList className="flex-wrap justify-start gap-2">
              <NavigationMenuItem>
                <Button
                  ref={guideTriggerRef}
                  variant="link"
                  size="sm"
                  className="h-auto p-0"
                  onClick={() => setGuideOpen(true)}
                >
                  使用指南
                </Button>
              </NavigationMenuItem>
              <NavigationMenuItem>
                <NavigationMenuLink asChild>
                  <Link href="/about">关于</Link>
                </NavigationMenuLink>
              </NavigationMenuItem>
              <NavigationMenuItem>
                <NavigationMenuLink asChild>
                  <Link href="/privacy">隐私</Link>
                </NavigationMenuLink>
              </NavigationMenuItem>
              <NavigationMenuItem>
                <NavigationMenuLink asChild>
                  <Link href="/terms">使用条款</Link>
                </NavigationMenuLink>
              </NavigationMenuItem>
              <NavigationMenuItem>
                <NavigationMenuLink asChild>
                  <Link href="/contact">联系</Link>
                </NavigationMenuLink>
              </NavigationMenuItem>
            </NavigationMenuList>
          </NavigationMenu>
        </LayoutContainer>
      </UI.Content>
      <UsageGuide
        view={guideOpen ? "guide" : null}
        onClose={() => setGuideOpen(false)}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          guideTriggerRef.current?.focus();
        }}
      />
    </>
  );
}
