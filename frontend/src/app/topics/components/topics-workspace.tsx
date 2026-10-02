"use client";

import Link from "next/link";
import { PlusIcon } from "lucide-react";

import { TopicList } from "@/components/monitors/topic-list";
import { Button } from "@/components/ui/button";

export function TopicsWorkspace() {
  return (
    <div>
      <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">
            我的关注
          </h1>
          <p className="text-muted-foreground mt-4 leading-7">
            设置关键词和来源，持续关注你关心的变化。
          </p>
        </div>
        <Button asChild size="lg" className="rounded-full">
          <Link href="/monitors/new">
            <PlusIcon data-icon="inline-start" />
            创建关注
          </Link>
        </Button>
      </div>
      <TopicList />
    </div>
  );
}
