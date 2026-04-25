"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { api, formatDate, Hotspot, Page } from "../lib/api";

export function HotspotsClient() {
  const [items, setItems] = useState<Hotspot[]>([]);
  const [importance, setImportance] = useState("");
  const [sort, setSort] = useState("fetched_at_desc");
  const [error, setError] = useState<string | null>(null);

  async function load(path = `/api/hotspots?sort=${sort}`) {
    const page = await api<Page<Hotspot>>(path);
    setItems(page.items);
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function applyFilters(event: FormEvent) {
    event.preventDefault();
    const params = new URLSearchParams({ sort });
    if (importance) params.set("importance", importance);
    await load(`/api/hotspots?${params.toString()}`);
  }

  return (
    <div className="grid gap-4">
      <form className="grid gap-3 rounded-lg border border-slate-300 bg-white p-3 md:grid-cols-[180px_180px_88px]" onSubmit={applyFilters}>
        <select className="min-h-10 rounded-md border border-slate-300 px-3" value={importance} onChange={(event) => setImportance(event.target.value)}>
          <option value="">全部重要性</option>
          <option value="high">high</option>
          <option value="medium">medium</option>
          <option value="low">low</option>
        </select>
        <select className="min-h-10 rounded-md border border-slate-300 px-3" value={sort} onChange={(event) => setSort(event.target.value)}>
          <option value="fetched_at_desc">抓取时间</option>
          <option value="published_at_desc">发布时间</option>
          <option value="relevance_desc">相关性</option>
          <option value="importance_desc">重要性</option>
        </select>
        <button className="min-h-10 rounded-md border border-teal-700 bg-teal-700 px-4 text-white" type="submit">筛选</button>
      </form>
      {error ? <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</p> : null}
      <div className="grid gap-3">
        {items.map((item) => (
          <article className="grid gap-3 rounded-lg border border-slate-300 bg-white p-4" key={item.id}>
            <div>
              <Link className="text-lg font-extrabold text-teal-800" href={`/hotspots/${item.id}`}>{item.title}</Link>
              <p className="mt-2 leading-relaxed text-slate-600">{item.ai_analysis?.summary || item.snippet || item.url}</p>
            </div>
            <div className="flex flex-wrap gap-3 text-sm text-slate-500">
              <span>{item.source?.name || item.source_id}</span>
              <span>{item.keyword?.keyword || "-"}</span>
              <span>{item.ai_analysis?.importance || "-"}</span>
              <span>{formatDate(item.published_at || item.fetched_at)}</span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
