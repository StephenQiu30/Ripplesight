"use client";
import * as UI from "@/components/ui/content";

import { Spinner } from "@/components/ui/spinner";
import { Item, ItemContent, ItemDescription } from "@/components/ui/item";
import { toast } from "sonner";

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
      if (cause instanceof ApiRequestError && cause.kind === "cancelled")
        return;
      if (captured === epoch.current)
        toast.error(
          `${cause instanceof ApiRequestError ? cause.message : "来源材料读取失败，请重新读取或重试当前页。"}${rows?.length ? " 已加载材料保留；当前页尚未读完。" : ""}`,
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
    <UI.Content
      as="section"
      className="flex flex-col gap-y-4"
      aria-label="来源最近材料"
    >
      <UI.Heading level={2} className="text-xl font-medium">
        {name} · 原材料
      </UI.Heading>
      <UI.Text className="text-muted-foreground text-sm leading-7">
        仅读取当前许可的原材料，不按公开精选状态筛选。分析状态表示原监控标注；编辑精选和发布状态请在对应管理页核验。读取不采集、不调用模型。
      </UI.Text>
      <Button
        variant="outline"
        disabled={!token || busy}
        onClick={() => void read(true)}
      >
        读取来源材料
      </Button>
      {busy ? (
        <Item role="status">
          <Spinner aria-hidden="true" />
          <ItemContent>
            <ItemDescription className="line-clamp-none">
              正在读取来源材料…
            </ItemDescription>
          </ItemContent>
        </Item>
      ) : null}
      {rows?.length === 0 ? (
        <UI.Text>此来源暂无当前可读材料；不代表来源历史为空。</UI.Text>
      ) : null}
      {rows ? (
        <>
          <UI.Text className="text-muted-foreground text-sm">
            已加载 {rows.length} 条
            {cursor ? "，还有后页" : "，当前分页已到末尾"}。
          </UI.Text>
          {rows.map((item) => (
            <Item variant="muted" key={item.id} asChild>
              <UI.Content as="article" className="flex flex-col gap-y-3 p-4">
                <ItemContent className="min-w-0 gap-3">
                  <UI.Text className="font-medium break-words">
                    {item.latest_observation.content_version?.title ||
                      item.latest_observation.content_version?.body?.slice(
                        0,
                        120,
                      ) ||
                      "可读材料暂无文字"}
                  </UI.Text>
                  <ItemDescription className="line-clamp-none">
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
                  </ItemDescription>
                  <ItemDescription className="line-clamp-none break-all">
                    作品编号 {item.id}
                  </ItemDescription>
                  <UI.Content className="flex flex-wrap gap-4 text-sm">
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
                  </UI.Content>
                </ItemContent>
              </UI.Content>
            </Item>
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
        <UI.Text className="text-muted-foreground text-sm">
          尚未读取此来源材料。
        </UI.Text>
      )}
    </UI.Content>
  );
}
