import * as UI from "@/components/ui/content";
import {
  contentOriginLabel,
  contentScopeLabel,
  contentSourceLabel,
  formatTime,
} from "@/app/content/components/content-presenters";
import { Badge } from "@/components/ui/badge";

export function ContentSources({
  content,
}: {
  content: HotKeyAPI.ContentRecordDetailView;
}) {
  const entries = content.readable_sources ?? [];
  if (entries.length === 0) return null;

  return (
    <UI.Content
      as="section"
      aria-labelledby="content-sources-heading"
      className="mt-10"
    >
      <UI.Heading
        level={2}
        id="content-sources-heading"
        className="text-xl font-medium"
      >
        来源与获取记录
      </UI.Heading>
      <UI.Text className="text-muted-foreground mt-2 text-sm leading-6">
        同一作品可从多个入口获取。以下记录按各来源当前的读取许可显示。
      </UI.Text>
      <UI.ContentList className="mt-6 divide-y">
        {entries.map((entry) => (
          <UI.ContentListItem
            key={entry.observation_id}
            className="py-5 first:pt-0"
          >
            <UI.Content className="flex flex-wrap items-center gap-2">
              <UI.Heading level={3} className="min-w-0 font-medium break-words">
                {contentSourceLabel(entry.source_key, entry.source_name)}
              </UI.Heading>
              {entry.text_scope && entry.text_origin ? (
                <>
                  <Badge variant="secondary">
                    {contentScopeLabel(entry.text_scope, entry.text_origin)}
                  </Badge>
                  <Badge variant="outline">
                    {contentOriginLabel(entry.text_origin)}
                  </Badge>
                </>
              ) : (
                <Badge variant="outline">未取得正文</Badge>
              )}
            </UI.Content>
            <UI.Content
              as="dl"
              className="mt-3 grid gap-3 text-sm sm:grid-cols-3"
            >
              <UI.Content>
                <UI.Content as="dt" className="text-muted-foreground">
                  来源发布时间
                </UI.Content>
                <UI.Content as="dd" className="mt-1">
                  {formatTime(entry.published_at)}
                </UI.Content>
              </UI.Content>
              <UI.Content>
                <UI.Content as="dt" className="text-muted-foreground">
                  观察时间
                </UI.Content>
                <UI.Content as="dd" className="mt-1">
                  {formatTime(entry.observed_at)}
                </UI.Content>
              </UI.Content>
              <UI.Content>
                <UI.Content as="dt" className="text-muted-foreground">
                  本机取得时间
                </UI.Content>
                <UI.Content as="dd" className="mt-1">
                  {formatTime(entry.received_at)}
                </UI.Content>
              </UI.Content>
            </UI.Content>
          </UI.ContentListItem>
        ))}
      </UI.ContentList>
      {content.readable_sources_truncated ? (
        <UI.Text className="text-muted-foreground mt-3 text-sm">
          当前展示最近 {entries.length} 条可读获取记录。
        </UI.Text>
      ) : null}
    </UI.Content>
  );
}
