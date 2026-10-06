"use client";
import * as UI from "@/components/ui/content";

import Link from "next/link";
import { PlusIcon } from "lucide-react";
import { useCallback, useState } from "react";

import { TopicList } from "@/components/monitors/topic-list";
import { TopicEditor } from "@/app/monitors/[topicId]/components/topic-editor";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export function TopicsWorkspace({
  topicId,
  workspace = false,
}: {
  topicId?: string;
  workspace?: boolean;
}) {
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
      <UI.Content className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <UI.Content className="flex flex-col gap-2">
          <UI.Heading level={1}>
            {workspace ? "我的工作台" : "监控主题"}
          </UI.Heading>
          <UI.Text tone="muted" size="sm">
            设置关键词与来源，查看运行结果和告警。采集遵循主题频率与来源限制。
          </UI.Text>
        </UI.Content>
        <Button asChild size="navigation">
          <Link href="/monitors/new">
            <PlusIcon data-icon="inline-start" />
            创建关注
          </Link>
        </Button>
      </UI.Content>
      <Separator />
      <UI.Content className="grid min-w-0 grid-cols-1 items-start gap-8 xl:grid-cols-3 xl:gap-12">
        <TopicList
          selectedTopicId={selectedTopicId}
          onFirstTopic={setFirstTopicId}
          updatedTopics={updatedTopics}
          onForbidden={setListForbidden}
        />
        {selectedTopicId && !listForbidden && (
          <UI.Content className="min-w-0 xl:col-span-2">
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
