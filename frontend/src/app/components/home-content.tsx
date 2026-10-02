"use client";

import { useRef, useState } from "react";
import { ChevronRightIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { UsageGuide, type UsageGuideView } from "@/layout/usage-guide";
import { HeroSection } from "./hero-section";

export function HomeContent() {
  const [infoView, setInfoView] = useState<UsageGuideView | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  function openInfo(view: UsageGuideView, trigger: HTMLElement) {
    triggerRef.current = trigger;
    setInfoView(view);
  }

  return (
    <div className="flex flex-1 flex-col">
      <div className="text-muted-foreground flex h-20 shrink-0 items-center justify-center gap-4 text-xs md:gap-10 md:text-sm 2xl:text-base">
        <span>从一个关注，开始了解变化。</span>
        <Button
          variant="ghost"
          size="announcement"
          onClick={(event) => openInfo("example", event.currentTarget)}
        >
          看看示例
          <ChevronRightIcon data-icon="inline-end" />
        </Button>
      </div>
      <HeroSection onExample={(trigger) => openInfo("example", trigger)} />
      <UsageGuide
        view={infoView}
        onClose={() => setInfoView(null)}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          triggerRef.current?.focus();
        }}
      />
    </div>
  );
}
