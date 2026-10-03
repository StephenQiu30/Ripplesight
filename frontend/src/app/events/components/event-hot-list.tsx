"use client";
import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
} from "@/components/ui/item";
import { Alert, AlertDescription } from "@/components/ui/alert";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ApiRequestError } from "@/request";
import { listHotEvents } from "@/api/shijian";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
export function EventHotList({ topicId }: { topicId?: string }) {
  const [items, setItems] = useState<HotKeyAPI.EventAttentionView[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void listHotEvents(topicId ? { topic_id: topicId } : {}, {
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) {
          setItems(data.items);
          setState("ready");
        }
      })
      .catch((error: unknown) => {
        if (
          !controller.signal.aborted &&
          !(error instanceof ApiRequestError && error.kind === "cancelled")
        ) {
          setState("error");
          toast.error("热榜读取失败，请重试。");
        }
      });
    return () => controller.abort();
  }, [topicId, retry]);
  return (
    <section className="mt-10" aria-labelledby="event-hot-heading">
      <h2 id="event-hot-heading" className="text-xl font-medium">
        48 小时独立来源热榜
      </h2>
      <p className="text-muted-foreground mt-3 text-sm">
        同一机构或来源组计一次，至少两个参与者并含编辑报道。
      </p>
      {state === "loading" ? (
        <Item className="mt-4" role="status">
          <Spinner aria-hidden="true" />
          <ItemContent>
            <ItemDescription className="line-clamp-none">
              正在读取热榜…
            </ItemDescription>
          </ItemContent>
        </Item>
      ) : state === "error" ? (
        <div className="mt-4">
          <Alert>
            <AlertDescription>热榜读取失败。</AlertDescription>
          </Alert>
          <Button
            variant="outline"
            className="mt-3"
            onClick={() => setRetry((value) => value + 1)}
          >
            重试热榜
          </Button>
        </div>
      ) : !items.length ? (
        <Empty className="mt-4">
          <EmptyHeader>
            <EmptyDescription>
              当前没有满足独立来源条件的事件。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <ItemGroup className="mt-5 grid gap-3 sm:grid-cols-2">
          {items.map((item, index) => (
            <Item
              role="listitem"
              variant="outline"
              key={item.event_id}
              className="p-4"
            >
              <ItemContent className="min-w-0 gap-3">
                <Link
                  className="font-medium underline-offset-4 hover:underline"
                  href={`/events/${item.event_id}`}
                >
                  {index + 1}. {item.representative?.title ?? "查看事件证据"}
                </Link>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge variant="secondary">热度 {item.heat.toFixed(1)}</Badge>
                  <Badge variant="secondary">
                    {item.participant_count} 个参与者
                  </Badge>
                  {!item.complete ? (
                    <Badge variant="outline">覆盖待补全</Badge>
                  ) : null}
                </div>
                <ItemDescription className="mt-3 line-clamp-none">
                  {item.source_names.join(" · ")}
                </ItemDescription>
              </ItemContent>
            </Item>
          ))}
        </ItemGroup>
      )}
    </section>
  );
}
