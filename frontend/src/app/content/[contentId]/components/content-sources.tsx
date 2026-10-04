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
    <section aria-labelledby="content-sources-heading" className="mt-10">
      <h2 id="content-sources-heading" className="text-xl font-medium">
        来源与获取记录
      </h2>
      <p className="text-muted-foreground mt-2 text-sm leading-6">
        同一作品可从多个入口获取。以下记录按各来源当前的读取许可显示。
      </p>
      <ul className="mt-6 divide-y">
        {entries.map((entry) => (
          <li key={entry.observation_id} className="py-5 first:pt-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="min-w-0 font-medium break-words">
                {contentSourceLabel(entry.source_key, entry.source_name)}
              </h3>
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
            </div>
            <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-muted-foreground">来源发布时间</dt>
                <dd className="mt-1">{formatTime(entry.published_at)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">观察时间</dt>
                <dd className="mt-1">{formatTime(entry.observed_at)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">本机取得时间</dt>
                <dd className="mt-1">{formatTime(entry.received_at)}</dd>
              </div>
            </dl>
          </li>
        ))}
      </ul>
      {content.readable_sources_truncated ? (
        <p className="text-muted-foreground mt-3 text-sm">
          当前展示最近 {entries.length} 条可读获取记录。
        </p>
      ) : null}
    </section>
  );
}
