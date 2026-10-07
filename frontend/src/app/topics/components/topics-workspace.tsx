"use client";
import * as UI from "@/components/ui/content";

import Link from "next/link";
import { PlusIcon } from "lucide-react";
import { useCallback, useState } from "react";

import { TopicList } from "@/components/monitors/topic-list";
import { TopicEditor } from "@/app/monitors/[topicId]/components/topic-editor";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

export function TopicsWorkspace({
  topicId,
  workspace = false,
}: {
  topicId?: string;
  workspace?: boolean;
}) {
  const [topicsOpen, setTopicsOpen] = useState(false);
  const [firstTopicId, setFirstTopicId] = useState<string>();
  const [listForbidden, setListForbidden] = useState(false);
  const [updatedTopics, setUpdatedTopics] = useState<
    Record<string, HotKeyAPI.MonitorTopicView>
  >({});
  const updateTopic = useCallback((topic: HotKeyAPI.MonitorTopicView) => {
    setUpdatedTopics((previous) => ({ ...previous, [topic.id]: topic }));
  }, []);
  const selectedTopicId = topicId ?? firstTopicId;
  return (
    <UI.Content className="flex min-w-0 flex-col gap-8">
      <UI.Content className="flex flex-wrap items-center justify-between gap-4">
        <UI.Content className="flex flex-col gap-2">
          <UI.Heading level={1}>
            {workspace ? "我的工作台" : "监控主题"}
          </UI.Heading>
          {
            <UI.Text tone="muted" size="sm">
              设置关键词与来源，查看运行结果和告警。采集遵循主题频率与来源限制。
            </UI.Text>
          }
        </UI.Content>
        <Button asChild size="navigation">
          <Link href="/monitors/new">
            <PlusIcon data-icon="inline-start" />
            新建主题
          </Link>
        </Button>
      </UI.Content>
      <UI.Content className="flex min-w-0 flex-col items-stretch gap-8 lg:flex-row">
        <Collapsible
          open={topicsOpen || !selectedTopicId || listForbidden}
          onOpenChange={setTopicsOpen}
          className="min-w-0 lg:w-80 lg:shrink-0"
        >
          <CollapsibleTrigger asChild className="mb-4 lg:hidden">
            <Button variant="outline">
              {topicsOpen ? "收起主题列表" : "切换监控主题"}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent
            forceMount
            className="data-[state=closed]:hidden lg:data-[state=closed]:block"
          >
            <TopicList
              selectedTopicId={selectedTopicId}
              onFirstTopic={setFirstTopicId}
              updatedTopics={updatedTopics}
              onForbidden={setListForbidden}
            />
          </CollapsibleContent>
        </Collapsible>
        {selectedTopicId && !listForbidden && (
          <UI.Content className="min-w-0 flex-1">
            <TopicEditor
              key={selectedTopicId}
              topicId={selectedTopicId}
              embedded
              onTopicChange={updateTopic}
            />
          </UI.Content>
        )}
      </UI.Content>
    </UI.Content>
  );
}
