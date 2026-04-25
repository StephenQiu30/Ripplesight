import Link from "next/link";
import type { HotspotEvent } from "@/lib/api-client";

type EventCardProps = {
  event: HotspotEvent;
};

export function EventCard({ event }: EventCardProps) {
  return (
    <article className="rounded-xl border border-slate-800 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-base font-semibold leading-tight text-cyan-100">
          <Link href={`/events/${encodeURIComponent(event.id)}`} className="hover:underline">
            {event.event_title}
          </Link>
        </h3>
        <span className="rounded-full border border-cyan-700 px-2 py-0.5 text-xs text-cyan-200">
          热度 {event.score.toFixed(2)}
        </span>
      </div>
      <p className="mt-2 text-sm text-slate-300">{event.summary_zh}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-300">
        <span className="rounded-full border border-slate-700 px-2 py-1">来源数 {event.source_count}</span>
        {(event.topic_tags ?? []).map((tag: string) => (
          <span key={`${event.id}-${tag}`} className="rounded-full border border-slate-700 px-2 py-1">
            {tag}
          </span>
        ))}
      </div>
    </article>
  );
}
