"use client";

import { useEffect, useState } from "react";
import { api, CheckRun, formatDate, Page } from "../lib/api";

export function RunsClient() {
  const [items, setItems] = useState<CheckRun[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const page = await api<Page<CheckRun>>("/api/check-runs");
    setItems(page.items);
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function triggerRun() {
    setRunning(true);
    setError(null);
    try {
      await api<CheckRun>("/api/check-runs", { method: "POST", body: JSON.stringify({ trigger_type: "manual" }) });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "触发失败");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="grid gap-4">
      <button className="w-fit rounded-md border border-teal-700 bg-teal-700 px-4 py-2 text-white disabled:opacity-60" type="button" onClick={triggerRun} disabled={running}>
        {running ? "运行中" : "手动检查"}
      </button>
      {error ? <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</p> : null}
      <div className="overflow-hidden rounded-lg border border-slate-300 bg-white">
        <div className="grid gap-3 bg-slate-50 p-3 text-sm font-bold text-slate-500 md:grid-cols-5">
          <span>触发</span>
          <span>状态</span>
          <span>成功</span>
          <span>失败</span>
          <span>开始</span>
        </div>
        {items.map((item) => (
          <div className="grid gap-3 border-t border-slate-200 p-3 md:grid-cols-5" key={item.id}>
            <span>{item.trigger_type}</span>
            <span className={item.status === "completed" ? "w-fit rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700" : "w-fit rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-700"}>{item.status}</span>
            <span>{item.success_count}</span>
            <span>{item.failure_count}</span>
            <span>{formatDate(item.started_at)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
