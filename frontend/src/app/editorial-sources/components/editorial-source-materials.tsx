"use client";
import { Alert, AlertDescription } from "@/components/ui/alert";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { listContentRecords } from "@/api/zuopinziliao";
import {
  formatTime,
  visibilityStatusLabel,
} from "@/app/content/components/content-presenters";
import { Button } from "@/components/ui/button";
import { ApiRequestError } from "@/request";

type Props = { token: string; sourceKey: string; name: string };
const states = {
  missing: "尚无标注",
  pending: "标注待执行",
  failed: "标注失败",
  invalid: "标注结果失效",
  valid: "已有有效标注",
};

export function EditorialSourceMaterials({ token, sourceKey, name }: Props) {
  const [rows, setRows] = useState<HotKeyAPI.ContentRecordSummaryView[] | null>(
    null,
  );
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const epoch = useRef(0);
  const loading = useRef(false);
  const controllers = useRef(new Set<AbortController>());
  useEffect(
    () => () => {
      epoch.current += 1;
      controllers.current.forEach((controller) => controller.abort());
    },
    [],
  );
  async function read(reset: boolean) {
    if (!token || loading.current) return;
    loading.current = true;
    setBusy(true);
    setError("");
    const captured = epoch.current;
    const controller = new AbortController();
    controllers.current.add(controller);
    try {
      const page = await listContentRecords(
        {
          source_key: sourceKey,
          limit: 20,
          ...(!reset && cursor ? { cursor } : {}),
        },
        {
          headers: { "X-HotKey-Operator-Token": token },
          signal: controller.signal,
        },
      );
      if (captured !== epoch.current) return;
      if (!reset && page.next_cursor && page.next_cursor === cursor)
        throw new Error("cursor");
      setRows((current) => {
        const values = reset ? page.items : [...(current ?? []), ...page.items];
        return Array.from(
          new Map(values.map((item) => [item.id, item])).values(),
        );
      });
      setCursor(page.next_cursor ?? null);
    } catch (cause) {
      if (captured === epoch.current)
        setError(
          cause instanceof ApiRequestError
            ? cause.message
            : "来源材料读取失败，请重新读取或重试当前页。",
        );
    } finally {
      controllers.current.delete(controller);
      if (captured === epoch.current) {
        loading.current = false;
        setBusy(false);
      }
    }
  }
  return (
    <section className="flex flex-col gap-y-4" aria-label="来源最近材料">
      <h2 className="text-xl font-medium">{name} · 原材料</h2>
      <p className="text-muted-foreground text-sm leading-7">
        仅读取当前许可的原材料，不按公开精选状态筛选。分析状态表示原监控标注；编辑精选和发布状态请在对应管理页核验。读取不采集、不调用模型。
      </p>
      <Button
        variant="outline"
        disabled={!token || busy}
        onClick={() => void read(true)}
      >
        读取来源材料
      </Button>
      {busy ? <p role="status">正在读取来源材料…</p> : null}
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>
            {error}
            {rows?.length ? " 已加载材料保留；当前页尚未读完。" : ""}
          </AlertDescription>
        </Alert>
      ) : null}
      {rows?.length === 0 ? (
        <p>此来源暂无当前可读材料；不代表来源历史为空。</p>
      ) : null}
      {rows ? (
        <>
          <p className="text-muted-foreground text-sm">
            已加载 {rows.length} 条
            {cursor ? "，还有后页" : "，当前分页已到末尾"}。
          </p>
          {rows.map((item) => (
            <article
              key={item.id}
              className="bg-muted/30 flex flex-col gap-y-3 rounded-xl p-4"
            >
              <p className="font-medium break-words">
                {item.latest_observation.content_version?.title ||
                  item.latest_observation.content_version?.body?.slice(
                    0,
                    120,
                  ) ||
                  "可读材料暂无文字"}
              </p>
              <p className="text-muted-foreground text-sm">
                {item.analysis_state
                  ? states[item.analysis_state]
                  : "未指定监控标注状态"}{" "}
                ·{" "}
                {item.current_visibility
                  ? visibilityStatusLabel(item.current_visibility.status)
                  : "可见性状态未知"}{" "}
                · 时间{" "}
                {formatTime(
                  item.timeline_at ??
                    item.latest_observation.published_at ??
                    item.latest_observation.observed_at,
                )}
              </p>
              <p className="text-muted-foreground text-xs break-all">
                作品编号 {item.id}
              </p>
              <div className="flex flex-wrap gap-4 text-sm">
                <Link
                  href={`/content/${item.id}`}
                  className="underline underline-offset-4"
                >
                  查看原材料 {item.id}
                </Link>
                <Link
                  href={`/publication/manage?content_id=${encodeURIComponent(item.id)}`}
                  className="underline underline-offset-4"
                >
                  编辑分析与发布 {item.id}
                </Link>
              </div>
            </article>
          ))}
          {cursor ? (
            <Button
              variant="outline"
              disabled={!token || busy}
              onClick={() => void read(false)}
            >
              读取更多材料
            </Button>
          ) : null}
        </>
      ) : (
        <p className="text-muted-foreground text-sm">尚未读取此来源材料。</p>
      )}
    </section>
  );
}
