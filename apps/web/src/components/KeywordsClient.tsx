"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, Keyword } from "../lib/api";

export function KeywordsClient() {
  const [items, setItems] = useState<Keyword[]>([]);
  const [keyword, setKeyword] = useState("");
  const [queryTemplate, setQueryTemplate] = useState("");
  const [priority, setPriority] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setItems(await api<Keyword[]>("/api/keywords"));
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function createKeyword(event: FormEvent) {
    event.preventDefault();
    await api<Keyword>("/api/keywords", {
      method: "POST",
      body: JSON.stringify({ keyword, query_template: queryTemplate || null, enabled: true, priority }),
    });
    setKeyword("");
    setQueryTemplate("");
    setPriority(0);
    await load();
  }

  async function toggleKeyword(id: number) {
    await api<Keyword>(`/api/keywords/${id}/toggle`, { method: "POST" });
    await load();
  }

  async function deleteKeyword(id: number) {
    await api<void>(`/api/keywords/${id}`, { method: "DELETE" });
    await load();
  }

  return (
    <div className="grid gap-4">
      <form className="grid gap-3 rounded-lg border border-slate-300 bg-white p-3 md:grid-cols-[1fr_1fr_120px_88px]" onSubmit={createKeyword}>
        <input className="min-h-10 rounded-md border border-slate-300 px-3" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="关键词" required />
        <input className="min-h-10 rounded-md border border-slate-300 px-3" value={queryTemplate} onChange={(event) => setQueryTemplate(event.target.value)} placeholder="查询模板" />
        <input className="min-h-10 rounded-md border border-slate-300 px-3" type="number" value={priority} onChange={(event) => setPriority(Number(event.target.value))} aria-label="优先级" />
        <button className="min-h-10 rounded-md border border-teal-700 bg-teal-700 px-4 text-white" type="submit">新增</button>
      </form>
      {error ? <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</p> : null}
      <div className="overflow-hidden rounded-lg border border-slate-300 bg-white">
        <div className="grid gap-3 bg-slate-50 p-3 text-sm font-bold text-slate-500 md:grid-cols-[1.2fr_1.2fr_.6fr_1fr]">
          <span>关键词</span>
          <span>模板</span>
          <span>状态</span>
          <span>操作</span>
        </div>
        {items.map((item) => (
          <div className="grid gap-3 border-t border-slate-200 p-3 md:grid-cols-[1.2fr_1.2fr_.6fr_1fr]" key={item.id}>
            <strong>{item.keyword}</strong>
            <span>{item.query_template || "-"}</span>
            <span className={item.enabled ? "w-fit rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700" : "w-fit rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500"}>{item.enabled ? "启用" : "停用"}</span>
            <span className="flex gap-2">
              <button className="rounded-md border border-slate-300 px-3 py-1" type="button" onClick={() => toggleKeyword(item.id)}>
                切换
              </button>
              <button className="rounded-md border border-slate-300 px-3 py-1" type="button" onClick={() => deleteKeyword(item.id)}>
                删除
              </button>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
