"use client";

import { useEffect, useState } from "react";
import { listRelatedEvents } from "@/api/shijian";
import * as UI from "@/components/ui/content";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemGroup,
} from "@/components/ui/item";
import { Skeleton } from "@/components/ui/skeleton";
import {
  EventEmpty,
  EventSectionFailure,
} from "@/components/events/event-reading";
import { ApiRequestError } from "@/request";

export function EventRelated({ eventId }: { eventId: string }) {
  const [items, setItems] = useState<HotKeyAPI.EventRelatedItemView[] | null>(
    null,
  );
  const [failure, setFailure] = useState<{ error: unknown } | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void listRelatedEvents({ event_id: eventId }, { signal: controller.signal })
      .then((page) => {
        if (!controller.signal.aborted) setItems(page.items);
      })
      .catch((error: unknown) => {
        if (
          !controller.signal.aborted &&
          !(error instanceof ApiRequestError && error.kind === "cancelled")
        )
          setFailure({ error });
      });
    return () => controller.abort();
  }, [eventId, retry]);
  return (
    <UI.Content
      as="section"
      className="flex flex-col gap-4"
      aria-labelledby="event-related-heading"
    >
      <UI.Heading id="event-related-heading">关联事件</UI.Heading>
      {failure ? (
        <EventSectionFailure
          title="无法读取关联事件"
          error={failure.error}
          retry={() => {
            setFailure(null);
            setRetry((value) => value + 1);
          }}
        />
      ) : items === null ? (
        <Skeleton
          aria-label="正在读取关联事件"
          className="h-24 w-full motion-reduce:animate-none"
        />
      ) : !items.length ? (
        <EventEmpty>尚无经过证据复验的关联事件。</EventEmpty>
      ) : (
        <ItemGroup>
          {items.map(({ event, supporting_report_count }) => (
            <Item key={event.id} role="listitem" className="px-0">
              <ItemContent className="min-w-0 gap-2">
                <UI.TextLink href={`/events/${event.id}`}>
                  {event.title ?? "关联事件摘要暂不可读"}
                </UI.TextLink>
                <ItemDescription>
                  <UI.InlineCode>{supporting_report_count}</UI.InlineCode>{" "}
                  篇独立联系报道
                </ItemDescription>
              </ItemContent>
            </Item>
          ))}
        </ItemGroup>
      )}
    </UI.Content>
  );
}
