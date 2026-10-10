"use client";

import { PageHeader } from "@/components/system/page-header";
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
  const [topicsOpen, setTopicsOpen] = useState(true);
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
      <PageHeader
        title={workspace ? "我的工作台" : "监控主题"}
        description="跟踪关键词，查看各平台的命中内容与讨论。"
        actions={
          <Button asChild size="navigation">
            <Link href="/monitors/new">
              <PlusIcon data-icon="inline-start" />
              新建主题
            </Link>
          </Button>
        }
      />
      <UI.Content className="flex min-w-0 flex-col items-stretch gap-8">
        <Collapsible
          open={topicsOpen || !selectedTopicId || listForbidden}
          onOpenChange={setTopicsOpen}
          className="min-w-0"
        >
          <CollapsibleTrigger asChild className="mb-4">
            <Button variant="outline">
              {topicsOpen ? "收起主题列表" : "切换监控主题"}
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent forceMount motion="height">
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
