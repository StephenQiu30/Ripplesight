import { Content, Heading, Text } from "@/components/ui/content";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { ObservationGap } from "@/components/ui/signal";
import type { TopicSourceOption } from "@/components/monitors/topic-settings-fields";

export function TopicOverview({
  topic,
  sources,
  onSourceChange,
}: {
  topic: HotKeyAPI.MonitorTopicView;
  sources: TopicSourceOption[];
  onSourceChange: (key: string, checked: boolean) => void;
}) {
  return (
    <Content layout="stack" className="gap-9">
      <Content
        as="section"
        aria-label="监控关键词"
        className="grid grid-cols-1 gap-6 sm:grid-cols-2"
      >
        <Content layout="stack" className="gap-2">
          <Text size="xs" tone="muted">
            包含关键词
          </Text>
          <Content layout="row">
            {[...topic.rules.match_any, ...topic.rules.match_all].map(
              (word) => (
                <Badge key={word} variant="secondary">
                  {word}
                </Badge>
              ),
            )}
          </Content>
          {topic.rules.match_all.length ? (
            <Text size="xs" tone="muted">
              同时包含：{topic.rules.match_all.join("、")}
            </Text>
          ) : null}
        </Content>
        <Content layout="stack" className="gap-2">
          <Text size="xs" tone="muted">
            排除关键词
          </Text>
          <Content layout="row">
            {topic.rules.exclude.length ? (
              topic.rules.exclude.map((word) => (
                <Badge key={word} variant="secondary">
                  {word}
                </Badge>
              ))
            ) : (
              <Text size="sm" tone="muted">
                未设置
              </Text>
            )}
          </Content>
        </Content>
      </Content>
      <Content as="section" aria-labelledby="hourly-hits" layout="stack">
        <Content className="flex items-center justify-between gap-4">
          <Heading level={3} appearance="sidebar" id="hourly-hits">
            每小时命中
          </Heading>
          <Text size="xs" tone="muted">
            过去 24 小时
          </Text>
        </Content>
        <ObservationGap>
          暂无小时统计。采集结果保留在下方“查看监控结果”。
        </ObservationGap>
      </Content>
      <Content
        as="section"
        aria-labelledby="collection-platforms"
        layout="stack"
      >
        <Content className="flex items-center justify-between gap-4">
          <Heading level={3} appearance="sidebar" id="collection-platforms">
            采集平台
          </Heading>
          <Text size="xs" tone="muted">
            每 {topic.collection_interval_seconds / 60} 分钟检索
          </Text>
        </Content>
        <Content layout="stack" className="gap-0">
          {sources.length ? (
            sources.map((source) => (
              <Content
                key={source.sourceKey}
                className="flex items-center justify-between gap-6 border-b py-4"
              >
                <Content layout="stack" className="min-w-0 gap-1">
                  <Text as="strong" size="sm">
                    {source.displayName}
                  </Text>
                  <Text size="xs" tone="muted">
                    {source.reason}
                  </Text>
                </Content>
                <Switch
                  aria-label={`${source.displayName}采集`}
                  checked={topic.source_keys.includes(source.sourceKey)}
                  disabled={!source.selectable || topic.status === "archived"}
                  onCheckedChange={(checked) =>
                    onSourceChange(source.sourceKey, checked)
                  }
                />
              </Content>
            ))
          ) : (
            <Text size="sm" tone="muted">
              暂无可用采集平台。
            </Text>
          )}
        </Content>
        <Text size="xs" tone="muted">
          更改平台后将在主题设置中确认并保存。
        </Text>
      </Content>
    </Content>
  );
}
