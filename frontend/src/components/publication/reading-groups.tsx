"use client";

import { useState } from "react";
import {
  getPublicFactReports,
  getPublicStoryDevelopments,
} from "@/api/gongkaifabu";
import {
  PublicItemCards,
  publicationTime,
} from "@/components/publication/reading-parts";
import { Button } from "@/components/ui/button";
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
  const [error, setError] = useState<string>();
  async function load(nextMode: "reports" | "developments", more = false) {
    setBusy(true);
    setError(undefined);
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
      setReports([]);
      setDevelopments([]);
      setCursor(null);
      setError(
        cause instanceof ApiRequestError && cause.status === 409
          ? "报道或许可已经变化，请重新展开。"
          : "暂时无法展开，请重新读取。",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-y-3">
      <div className="flex flex-wrap gap-2">
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
      </div>
      {mode ? (
        <section
          aria-live="polite"
          className="bg-muted/30 rounded-lg border p-4"
        >
          {busy ? <p role="status">正在读取当前许可…</p> : null}
          {error ? (
            <div role="status">
              <p>{error}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void load(mode)}
              >
                重新展开
              </Button>
            </div>
          ) : null}
          {!error && mode === "reports" ? (
            <PublicItemCards items={reports} />
          ) : null}
          {!error && mode === "developments"
            ? developments.map((entry) => (
                <section key={entry.fact_id}>
                  <p className="text-muted-foreground text-xs">
                    {publicationTime(entry.anchor_at)} · {entry.report_count}{" "}
                    篇公开报道
                  </p>
                  <PublicItemCards items={[entry.representative]} />
                </section>
              ))
            : null}
          {cursor && !busy && !error ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => void load(mode, true)}
            >
              加载更多
            </Button>
          ) : null}
        </section>
      ) : null}
    </div>
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
    <div>
      {page.cards.map((card, index) => (
        <section key={card.key}>
          {!index ||
          day(page.cards[index - 1].anchor_at) !== day(card.anchor_at) ? (
            <h2 className="bg-muted/50 mt-5 rounded-md px-3 py-2 text-sm font-medium">
              {day(card.anchor_at)} ·{" "}
              {String(page.day_counts?.[day(card.anchor_at)] ?? "")} 条精选
            </h2>
          ) : null}
          <PublicItemCards items={[card.item]} />
          {card.group?.latest_development ? (
            <p className="text-muted-foreground mb-3 text-sm">
              最新进展 · {card.group.latest_development.title}
            </p>
          ) : null}
          {card.group ? (
            <GroupExpansion group={card.group} filters={page.filters} />
          ) : null}
        </section>
      ))}
    </div>
  );
}
