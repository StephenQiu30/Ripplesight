"use client";

import Link from "next/link";
import {
  FileTextIcon,
  ListChecksIcon,
  NewspaperIcon,
  PlusIcon,
  RadioIcon,
  TrendingUpIcon,
} from "lucide-react";

import { BrandLockup } from "@/components/brand/brand-lockup";
import { TopicList } from "@/components/monitors/topic-list";
import { Button } from "@/components/ui/button";

export function EventsWorkspace() {
  return (
    <div className="bg-background min-h-screen">
      <header className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8 xl:px-16 2xl:px-0">
        <BrandLockup href="/events" compactOnMobile />
        <div className="flex items-center gap-2">
          <Button
            asChild
            variant="ghost"
            size="icon"
            className="sm:h-11 sm:w-auto sm:px-3 md:h-8 md:px-2.5"
          >
            <Link href="/content">
              <FileTextIcon className="sm:hidden" aria-hidden="true" />
              <span className="sr-only sm:not-sr-only">作品资料</span>
            </Link>
          </Button>
          <Button
            asChild
            variant="ghost"
            size="icon"
            className="sm:h-11 sm:w-auto sm:px-3 md:h-8 md:px-2.5"
          >
            <Link href="/sources">
              <RadioIcon className="sm:hidden" aria-hidden="true" />
              <span className="sr-only sm:not-sr-only">来源状态</span>
            </Link>
          </Button>
          <Button
            asChild
            variant="ghost"
            size="icon"
            className="sm:h-11 sm:w-auto sm:px-3 md:h-8 md:px-2.5"
          >
            <Link href="/hotlists">
              <TrendingUpIcon className="sm:hidden" aria-hidden="true" />
              <span className="sr-only sm:not-sr-only">热榜历史</span>
            </Link>
          </Button>
          <Button
            asChild
            variant="ghost"
            size="icon"
            className="sm:h-11 sm:w-auto sm:px-3 md:h-8 md:px-2.5"
          >
            <Link href="/jobs">
              <ListChecksIcon className="sm:hidden" aria-hidden="true" />
              <span className="sr-only sm:not-sr-only">任务记录</span>
            </Link>
          </Button>
          <Button
            asChild
            variant="ghost"
            size="icon"
            className="sm:h-11 sm:w-auto sm:px-3 md:h-8 md:px-2.5"
          >
            <Link href="/reports">
              <NewspaperIcon className="sm:hidden" aria-hidden="true" />
              <span className="sr-only sm:not-sr-only">日报</span>
            </Link>
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-5 py-12 sm:px-8 sm:py-16 xl:px-16 2xl:px-0">
        <div className="flex flex-col gap-8 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-2xl">
            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
              从关键词开始关注
            </h1>
            <p className="text-muted-foreground mt-5 leading-7">
              创建你关心的品牌、产品或话题，按可用来源汇集相关讨论。
            </p>
          </div>
          <Button asChild size="lg">
            <Link href="/monitors/new">
              <PlusIcon data-icon="inline-start" />
              新建监控主题
            </Link>
          </Button>
        </div>
        <TopicList />
        <section className="border-border mt-24 border-t pt-8">
          <h2 className="text-xl font-semibold tracking-tight">事件脉络</h2>
          <p className="text-muted-foreground mt-3 max-w-2xl text-sm leading-7">
            事件归并仍在建设中。后续可沿时间与来源查看同一主题下的事件发展。
          </p>
        </section>
      </main>
    </div>
  );
}
