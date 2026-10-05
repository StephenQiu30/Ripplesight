"use client";
import * as UI from "@/components/ui/content";

import Link from "next/link";
import { PlusIcon } from "lucide-react";

import { TopicList } from "@/components/monitors/topic-list";
import { Button } from "@/components/ui/button";

export function TopicsWorkspace() {
  return (
    <UI.Content>
      <UI.Content className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <UI.Content>
          <UI.Heading
            level={1}
            className="text-3xl font-medium tracking-tight sm:text-4xl"
          >
            我的关注
          </UI.Heading>
          <UI.Text className="text-muted-foreground mt-4 leading-7">
            设置关键词和来源，持续关注你关心的变化。
          </UI.Text>
        </UI.Content>
        <Button asChild size="lg" className="rounded-full">
          <Link href="/monitors/new">
            <PlusIcon data-icon="inline-start" />
            创建关注
          </Link>
        </Button>
      </UI.Content>
      <TopicList />
    </UI.Content>
  );
}
