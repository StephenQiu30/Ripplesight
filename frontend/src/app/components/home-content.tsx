"use client";

import { useRef, useState } from "react";
import { ChevronRightIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CapabilityOverview, type HomeInfoView } from "./capability-overview";
import { HeroSection } from "./hero-section";
import { SiteHeader } from "./site-header";

export function HomeContent() {
  const [infoView, setInfoView] = useState<HomeInfoView | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  function openInfo(view: HomeInfoView, trigger: HTMLElement) {
    triggerRef.current = trigger;
    setInfoView(view);
  }

  return (
    <div className="bg-muted flex min-h-svh flex-col">
      <SiteHeader onGuide={(trigger) => openInfo("guide", trigger)} />
      <div className="text-muted-foreground flex h-20 shrink-0 items-center justify-center gap-4 px-5 text-xs md:gap-10 md:text-sm 2xl:text-base">
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
      <footer className="mx-auto flex w-full max-w-384 shrink-0 items-end justify-between gap-5 px-5 pt-8 pb-6 text-xs sm:px-8 md:h-22 md:items-center md:gap-6 md:pt-0 md:pb-5.5 md:text-sm 2xl:px-7 2xl:text-lg">
        <div className="flex max-w-72 flex-wrap items-center gap-x-5 gap-y-3 md:max-w-none md:gap-7 2xl:gap-12">
          <span className="text-muted-foreground basis-full text-xs md:basis-auto 2xl:text-base">
            信息来源示例
          </span>
          <span>Hacker News</span>
          <span>Google News</span>
          <span>36Kr</span>
        </div>
        <span className="text-muted-foreground whitespace-nowrap 2xl:text-base">
          来源能力以配置为准
        </span>
      </footer>
      <CapabilityOverview
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
