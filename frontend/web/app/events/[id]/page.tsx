import Link from "next/link";
import { getEventById } from "@/lib/api-client";
import { FeedbackForm } from "@/components/FeedbackForm";
import { MetaView } from "@/components/MetaView";

type Props = {
  params: {
    id: string;
  };
};

export default async function EventDetailPage({ params }: Props) {
  let event = null;
  let errorMessage = "";

  try {
    event = await getEventById(params.id);
  } catch (error) {
    errorMessage = error instanceof Error ? error.message : "获取事件失败";
  }

  if (!event) {
    return <div className="rounded-xl border border-slate-800 p-4 text-sm text-rose-300">未找到事件：{errorMessage}</div>;
  }

  return (
    <section className="space-y-3">
      <Link href="/events" className="text-sm text-cyan-300 hover:underline">
        ← 返回列表
      </Link>
      <h1 className="text-xl font-semibold">{event.event_title}</h1>
      <p className="text-sm text-slate-300">{event.summary_zh}</p>
      <div className="grid gap-2 md:grid-cols-2">
        <MetaView label="状态" value={event.status} />
        <MetaView label="热度分" value={event.score.toFixed(2)} />
        <MetaView label="来源数量" value={event.source_count} />
        <MetaView label="首次出现" value={event.first_seen_at} />
        <MetaView label="最后出现" value={event.last_seen_at} />
      </div>
      <div>
        <div className="mb-2 text-sm font-medium">标签</div>
        <div className="flex flex-wrap gap-2">
        {(event.topic_tags ?? []).map((tag: string) => (
            <span key={tag} className="rounded-full border border-slate-700 px-2 py-1 text-xs text-slate-300">
              {tag}
            </span>
          ))}
        </div>
      </div>
      <div>
        <div className="mb-2 text-sm font-medium">证据链</div>
        {event.evidence_links.length === 0 ? (
          <div className="text-sm text-slate-400">暂无证据链接</div>
        ) : (
          <ul className="list-inside list-disc space-y-1 text-sm">
            {event.evidence_links.map((url: string) => (
              <li key={url}>
                <a href={url} target="_blank" rel="noreferrer" className="text-cyan-300 underline">
                  {url}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
      <FeedbackForm targetId={event.id} targetType="event" />
    </section>
  );
}
