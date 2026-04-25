"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, Setting } from "../lib/api";

export function SettingsClient() {
  const [items, setItems] = useState<Setting[]>([]);
  const [key, setKey] = useState("daily_digest");
  const [value, setValue] = useState('{"enabled":true}');
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setItems(await api<Setting[]>("/api/settings"));
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function saveSetting(event: FormEvent) {
    event.preventDefault();
    await api<Setting>(`/api/settings/${key}`, {
      method: "PUT",
      body: JSON.stringify({ value: JSON.parse(value || "{}"), description: description || null }),
    });
    await load();
  }

  return (
    <div className="grid gap-4">
      <form className="grid gap-3 rounded-lg border border-slate-300 bg-white p-3 md:grid-cols-[1fr_2fr_1fr_88px]" onSubmit={saveSetting}>
        <input className="min-h-10 rounded-md border border-slate-300 px-3" value={key} onChange={(event) => setKey(event.target.value)} placeholder="key" required />
        <input className="min-h-10 rounded-md border border-slate-300 px-3" value={value} onChange={(event) => setValue(event.target.value)} placeholder="JSON value" />
        <input className="min-h-10 rounded-md border border-slate-300 px-3" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="描述" />
        <button className="min-h-10 rounded-md border border-teal-700 bg-teal-700 px-4 text-white" type="submit">保存</button>
      </form>
      {error ? <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</p> : null}
      <div className="overflow-hidden rounded-lg border border-slate-300 bg-white">
        {items.map((item) => (
          <div className="grid gap-3 border-t border-slate-200 p-3 first:border-t-0 md:grid-cols-[1fr_2fr_1fr]" key={item.key}>
            <strong>{item.key}</strong>
            <code className="truncate text-xs text-slate-500">{JSON.stringify(item.value)}</code>
            <span>{item.description || "-"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
