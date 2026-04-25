"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, Source } from "../lib/api";

export function SourcesClient() {
  const [items, setItems] = useState<Source[]>([]);
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState("rss");
  const [config, setConfig] = useState('{"url":"https://hnrss.org/frontpage","limit":20}');
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setItems(await api<Source[]>("/api/sources"));
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function createSource(event: FormEvent) {
    event.preventDefault();
    await api<Source>("/api/sources", {
      method: "POST",
      body: JSON.stringify({ name, source_type: sourceType, enabled: true, config: JSON.parse(config || "{}") }),
    });
    setName("");
    await load();
  }

  async function toggleSource(id: number) {
    await api<Source>(`/api/sources/${id}/toggle`, { method: "POST" });
    await load();
  }

  return (
    <div className="grid gap-4">
      <form className="grid gap-3 rounded-lg border border-slate-300 bg-white p-3 md:grid-cols-[1fr_160px_2fr_88px]" onSubmit={createSource}>
        <input className="min-h-10 rounded-md border border-slate-300 px-3" value={name} onChange={(event) => setName(event.target.value)} placeholder="来源名称" required />
        <select className="min-h-10 rounded-md border border-slate-300 px-3" value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
          <option value="rss">RSS</option>
          <option value="hacker_news">Hacker News</option>
        </select>
        <input className="min-h-10 rounded-md border border-slate-300 px-3" value={config} onChange={(event) => setConfig(event.target.value)} placeholder="JSON 配置" />
        <button className="min-h-10 rounded-md border border-teal-700 bg-teal-700 px-4 text-white" type="submit">新增</button>
      </form>
      {error ? <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</p> : null}
      <div className="overflow-hidden rounded-lg border border-slate-300 bg-white">
        <div className="grid gap-3 bg-slate-50 p-3 text-sm font-bold text-slate-500 md:grid-cols-[1fr_1fr_2fr_.6fr_.7fr]">
          <span>名称</span>
          <span>类型</span>
          <span>配置</span>
          <span>状态</span>
          <span>操作</span>
        </div>
        {items.map((item) => (
          <div className="grid gap-3 border-t border-slate-200 p-3 md:grid-cols-[1fr_1fr_2fr_.6fr_.7fr]" key={item.id}>
            <strong>{item.name}</strong>
            <span>{item.source_type}</span>
            <code className="truncate text-xs text-slate-500">{JSON.stringify(item.config)}</code>
            <span className={item.enabled ? "w-fit rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700" : "w-fit rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500"}>{item.enabled ? "启用" : "停用"}</span>
            <button className="rounded-md border border-slate-300 px-3 py-1" type="button" onClick={() => toggleSource(item.id)}>
              切换
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
