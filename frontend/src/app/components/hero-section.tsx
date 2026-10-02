import Image from "next/image";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useIdentitySession } from "@/components/auth/session-context";

type HeroSectionProps = {
  onExample: (trigger: HTMLElement) => void;
};

export function HeroSection({ onExample }: HeroSectionProps) {
  const session = useIdentitySession();
  return (
    <section
      className="relative flex w-full flex-col items-start gap-9 pt-10 pb-8 md:min-h-108 md:flex-1 md:flex-row md:items-center md:justify-between md:gap-0 md:pt-0 md:pb-12 2xl:min-h-125"
      aria-label="关注关键词，了解变化"
    >
      <div className="relative max-w-full md:w-3/5">
        <h1 className="text-3xl leading-snug font-light tracking-tight sm:text-4xl md:text-5xl md:leading-tight xl:text-6xl 2xl:text-7xl">
          关注你在意的，
          <br />
          看见新的变化。
        </h1>
        <div className="mt-7 flex items-center gap-3 md:mt-8 md:gap-3.5">
          <Button asChild size="hero">
            <Link href={session ? "/topics" : "/login"}>
              {session ? "进入系统" : "开始使用"}
            </Link>
          </Button>
          <Button
            variant="outline"
            size="hero"
            onClick={(event) => onExample(event.currentTarget)}
          >
            看看示例
          </Button>
        </div>
      </div>
      <Image
        src="/brand/hero-brand-soft.png"
        alt=""
        aria-hidden="true"
        width={366}
        height={366}
        preload
        sizes="(min-width:1536px) 368px, (min-width:1280px) 320px, 256px"
        className="pointer-events-none -mt-4 -mb-3 size-64 self-center object-contain md:absolute md:top-1/2 md:left-11/20 md:-mt-8 md:mb-0 md:-translate-x-1/2 md:-translate-y-1/2 lg:left-1/2 xl:size-80 2xl:size-92"
      />
      <div className="relative flex flex-col gap-2 text-sm leading-relaxed md:w-56 md:gap-3.5 md:text-base xl:w-72 xl:text-lg 2xl:w-88 2xl:text-xl">
        <p>选择你关心的话题</p>
        <p>简单设置，持续关注</p>
        <p>沿着来源，理解变化</p>
      </div>
    </section>
  );
}
