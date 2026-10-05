"use client";
import * as UI from "@/components/ui/content";

import { Spinner } from "@/components/ui/spinner";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";

import { useState } from "react";
import { toast } from "sonner";
import {
  getPublicFactReports,
  getPublicStoryDevelopments,
} from "@/api/gongkaifabu";
import {
  PublicItemCards,
  publicationTime,
} from "@/components/publication/reading-parts";
import { Button } from "@/components/ui/button";
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { ApiRequestError } from "@/request";

export function GroupExpansion({
  group,
  filters,
}: {
  group: Pick<HotKeyAPI.PublicReadingGroupView, "fact_id" | "event_id"> &
    Partial<
      Pick<
        HotKeyAPI.PublicReadingGroupView,
        "additional_source_count" | "development_count"
      >
    >;
  filters: HotKeyAPI.PublicReadingFilters;
}) {
  const [mode, setMode] = useState<"reports" | "developments" | null>(null);
  const [reports, setReports] = useState<HotKeyAPI.PublicItemView[]>([]);
  const [developments, setDevelopments] = useState<
    HotKeyAPI.PublicDevelopmentView[]
  >([]);
  const [revision, setRevision] = useState<string>();
  const [cursor, setCursor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  async function load(nextMode: "reports" | "developments", more = false) {
    setBusy(true);
    setFailed(false);
    setMode(nextMode);
    try {
      if (nextMode === "reports") {
        const page = await getPublicFactReports({
          ...filters,
          fact_id: group.fact_id,
          limit: 20,
          cursor: more ? cursor : undefined,
          revision: more ? revision : undefined,
        });
        setReports((old) => (more ? [...old, ...page.reports] : page.reports));
        setRevision(page.revision);
        setCursor(page.next_cursor);
      } else if (group.event_id) {
        const page = await getPublicStoryDevelopments({
          ...filters,
          event_id: group.event_id,
          limit: 20,
          cursor: more ? cursor : undefined,
          revision: more ? revision : undefined,
        });
        setDevelopments((old) =>
          more ? [...old, ...page.developments] : page.developments,
        );
        setRevision(page.revision);
        setCursor(page.next_cursor);
      }
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.kind === "cancelled")
        return;
      setReports([]);
      setDevelopments([]);
      setCursor(null);
      setFailed(true);
      toast.error(
        cause instanceof ApiRequestError && cause.status === 409
          ? "报道或许可已经变化，请重新展开。"
          : "暂时无法展开，请重新读取。",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <UI.Content className="flex flex-col gap-y-3">
      <UI.Content className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => {
            if (mode === "reports") setMode(null);
            else void load("reports");
          }}
        >
          {mode === "reports"
            ? "收起报道"
            : `展开同事实报道${group.additional_source_count ? ` · +${group.additional_source_count} 个来源` : ""}`}
        </Button>
        {group.event_id &&
        (group.development_count === undefined ||
          group.development_count > 1) ? (
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => {
              if (mode === "developments") setMode(null);
              else void load("developments");
            }}
          >
            {mode === "developments"
              ? "收起进展"
              : group.development_count === undefined
                ? "展开事实与进展"
                : `展开 ${group.development_count} 个事实与进展`}
          </Button>
        ) : null}
      </UI.Content>
      {mode ? (
        <Item variant="muted" asChild>
          <UI.Content as="section" aria-live="polite" className="p-4">
            <ItemContent className="min-w-0 gap-3">
              {busy ? (
                <Item role="status">
                  <Spinner aria-hidden="true" />
                  <ItemContent>
                    <ItemDescription className="line-clamp-none">
                      正在读取当前许可…
                    </ItemDescription>
                  </ItemContent>
                </Item>
              ) : null}
              {failed ? (
                <Empty>
                  <EmptyHeader>
                    <EmptyTitle>展开内容暂不可读</EmptyTitle>
                  </EmptyHeader>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => void load(mode)}
                  >
                    重新展开
                  </Button>
                </Empty>
              ) : null}
              {!failed && mode === "reports" ? (
                <PublicItemCards items={reports} />
              ) : null}
              {!failed && mode === "developments"
                ? developments.map((entry) => (
                    <UI.Content as="section" key={entry.fact_id}>
                      <UI.Text className="text-muted-foreground text-xs">
                        {publicationTime(entry.anchor_at)} ·{" "}
                        {entry.report_count} 篇公开报道
                      </UI.Text>
                      <PublicItemCards items={[entry.representative]} />
                    </UI.Content>
                  ))
                : null}
              {cursor && !busy && !failed ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void load(mode, true)}
                >
                  加载更多
                </Button>
              ) : null}
            </ItemContent>
          </UI.Content>
        </Item>
      ) : null}
    </UI.Content>
  );
}

export function PublicTimelineCards({
  page,
}: {
  page: HotKeyAPI.PublicTimelinePage;
}) {
  const day = (at: string) =>
    new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai" }).format(
      new Date(at),
    );
  if (!page.cards.length) return <PublicItemCards items={[]} />;
  return (
    <UI.Content>
      {page.cards.map((card, index) => (
        <UI.Content as="section" key={card.key}>
          {!index ||
          day(page.cards[index - 1].anchor_at) !== day(card.anchor_at) ? (
            <Item variant="muted" className="mt-5">
              <ItemTitle>
                <UI.Heading level={2}>
                  {day(card.anchor_at)} ·{" "}
                  {String(page.day_counts?.[day(card.anchor_at)] ?? "")} 条精选
                </UI.Heading>
              </ItemTitle>
            </Item>
          ) : null}
          <PublicItemCards items={[card.item]} />
          {card.group?.latest_development ? (
            <UI.Text className="text-muted-foreground mb-3 text-sm">
              最新进展 · {card.group.latest_development.title}
            </UI.Text>
          ) : null}
          {card.group ? (
            <GroupExpansion group={card.group} filters={page.filters} />
          ) : null}
        </UI.Content>
      ))}
    </UI.Content>
  );
}
