"use client";

import { useEffect, useState } from "react";
import { api, formatDate, Notification, Page } from "../lib/api";

export function NotificationsClient() {
  const [items, setItems] = useState<Notification[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Page<Notification>>("/api/notifications").then((page) => setItems(page.items)).catch((err) => setError(err.message));
  }, []);

  return (
    <div className="grid gap-4">
      {error ? <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{error}</p> : null}
      <div className="overflow-hidden rounded-lg border border-slate-300 bg-white">
        <div className="grid gap-3 bg-slate-50 p-3 text-sm font-bold text-slate-500 md:grid-cols-4">
          <span>渠道</span>
          <span>收件人</span>
          <span>状态</span>
          <span>时间</span>
        </div>
        {items.map((item) => (
          <div className="grid gap-3 border-t border-slate-200 p-3 md:grid-cols-4" key={item.id}>
            <span>{item.channel}</span>
            <span>{item.recipient || "-"}</span>
            <span className={item.status === "sent" ? "w-fit rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700" : "w-fit rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500"}>{item.status}</span>
            <span>{formatDate(item.sent_at || item.created_at)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
