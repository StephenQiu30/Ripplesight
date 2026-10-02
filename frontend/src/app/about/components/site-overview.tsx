"use client";

import { useEffect, useState } from "react";

import { getPublicSiteMeta, getPublicSiteStatistics } from "@/api/zhandiziliao";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";

export function SiteOverview() {
  const [meta, setMeta] = useState<HotKeyAPI.PublicSiteMetaView | null>(null);
  const [stats, setStats] = useState<HotKeyAPI.PublicSiteStatisticsView | null>(
    null,
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getPublicSiteMeta({ signal: controller.signal }),
      getPublicSiteStatistics({ signal: controller.signal }),
    ])
      .then(([nextMeta, nextStats]) => {
        if (controller.signal.aborted) return;
        setMeta(nextMeta);
        setStats(nextStats);
      })
      .catch((failure) => {
        if (controller.signal.aborted) return;
        if (failure instanceof ApiRequestError && failure.kind === "cancelled")
          return;
        setError("当前信息读取失败，请重试。旧统计不代表当前可见资料。");
        setStats(null);
        setMeta(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [refresh]);
  return (
    <section aria-label="当前站点状态" className="space-y-5">
      {busy && <p role="status">正在读取当前公开范围…</p>}
      {error && <p role="alert">{error}</p>}
      {meta && (
        <p>
          {meta.name} · {meta.version} · {meta.description}
        </p>
      )}
      {stats && (
        <dl className="grid grid-cols-2 gap-5 sm:grid-cols-3">
          <div>
            <dt>公开资料</dt>
            <dd className="text-foreground text-xl">{stats.visible_items}</dd>
          </div>
          <div>
            <dt>精选资料</dt>
            <dd className="text-foreground text-xl">{stats.selected_items}</dd>
          </div>
          <div>
            <dt>可见来源</dt>
            <dd className="text-foreground text-xl">{stats.visible_sources}</dd>
          </div>
        </dl>
      )}
      {meta && (
        <p>
          模型分析：{meta.features.editorial_analysis ? "启用" : "未启用"}
          ；公告监控：{meta.features.codex_monitor ? "启用" : "未启用"}；通知：
          {meta.features.notifications ? "启用" : "未启用"}。
        </p>
      )}
      <Button
        variant="outline"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setError("");
          setRefresh((value) => value + 1);
        }}
      >
        重新读取
      </Button>
    </section>
  );
}
