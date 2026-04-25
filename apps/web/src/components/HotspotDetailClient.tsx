"use client";

import { useEffect, useState } from "react";
import { api, formatDate, Hotspot } from "../lib/api";

export function HotspotDetailClient({ id }: { id: string }) {
  const [item, setItem] = useState<Hotspot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Hotspot>(`/api/hotspots/${id}`).then(setItem).catch((err) => setError(err.message));
  }, [id]);

  if (error) return <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</p>;
  if (!item) return <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-700">加载中</p>;

  return (
    <article className="rounded-lg border border-slate-300 bg-white p-5">
      <a className="mb-4 inline-block text-2xl font-extrabold text-teal-800" href={item.url} target="_blank" rel="noreferrer">
        {item.title}
      </a>
      <p className="leading-relaxed text-slate-600">{item.ai_analysis?.summary || item.snippet}</p>
      <dl className="mt-5 grid gap-3 md:grid-cols-[120px_1fr]">
        <dt className="font-bold text-slate-500">来源</dt>
        <dd>{item.source?.name || item.source_id}</dd>
        <dt className="font-bold text-slate-500">关键词</dt>
        <dd>{item.keyword?.keyword || "-"}</dd>
        <dt className="font-bold text-slate-500">相关性</dt>
        <dd>{item.ai_analysis?.relevance_score || "-"}</dd>
        <dt className="font-bold text-slate-500">理由</dt>
        <dd>{item.ai_analysis?.relevance_reason || "-"}</dd>
        <dt className="font-bold text-slate-500">时间</dt>
        <dd>{formatDate(item.published_at || item.fetched_at)}</dd>
      </dl>
    </article>
  );
}
