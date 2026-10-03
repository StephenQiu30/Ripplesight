"use client";
import { Input } from "@/components/ui/input";
import { FieldLabel, Field } from "@/components/ui/field";

import Link from "next/link";
import { useId, useState } from "react";
import { toast } from "sonner";
import { ApiRequestError } from "@/request";
import {
  getPublicDailyCalendar,
  listPublicEditionCatalogue,
} from "@/api/gongkaikanwumulu";
import { publicationTime } from "@/components/publication/reading-parts";
import { Button } from "@/components/ui/button";
const labels = { daily: "日报", weekly: "周报", monthly: "月报" } as const;

export function PublicEditionCatalogue({
  initial,
  initialCalendar,
}: {
  initial: HotKeyAPI.PublicEditionCatalogueView;
  initialCalendar?: HotKeyAPI.PublicDailyCalendarView;
}) {
  const fieldId = useId();

  const [entries, setEntries] = useState(initial.entries);
  const [next, setNext] = useState(initial.next_before_key);
  const [calendar, setCalendar] = useState(initialCalendar);
  const [month, setMonth] = useState(initialCalendar?.month ?? "");
  const [busy, setBusy] = useState(false);
  async function more() {
    if (!next) return;
    setBusy(true);
    try {
      const page = await listPublicEditionCatalogue({
        kind: initial.kind,
        before_key: next,
        limit: 20,
      });
      setEntries((old) => [
        ...old,
        ...page.entries.filter(
          (entry) => !old.some((before) => before.key === entry.key),
        ),
      ]);
      setNext(page.next_before_key);
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      toast.error("暂时无法读取更多刊期，请重试。");
    } finally {
      setBusy(false);
    }
  }
  async function loadMonth() {
    setBusy(true);
    setCalendar(undefined);
    try {
      setCalendar(await getPublicDailyCalendar({ month }));
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      toast.error("暂时无法读取月份日历，请检查月份或重试。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-y-8">
      <h1 className="text-3xl font-medium">{labels[initial.kind]}历史</h1>
      <nav aria-label="公开刊物" className="flex flex-wrap gap-5 text-sm">
        {(["daily", "weekly", "monthly"] as const).map((kind) => (
          <Link
            key={kind}
            href={`/reports/${kind}/archive`}
            aria-current={kind === initial.kind ? "page" : undefined}
          >
            {labels[kind]}历史
          </Link>
        ))}
        <Link href={`/reports/${initial.kind}`}>
          最新{labels[initial.kind]}
        </Link>
      </nav>
      {initial.kind === "daily" ? (
        <section
          aria-label="日报月份日历"
          className="flex flex-col gap-y-4 rounded-lg border p-5"
        >
          <h2 className="font-medium">月份日历</h2>
          <div className="flex flex-wrap items-end gap-3">
            <Field className="w-full min-w-0 sm:w-auto">
              <FieldLabel htmlFor={`${fieldId}-edition-catalogue-field-1`}>
                月份
              </FieldLabel>
              <Input
                aria-label="日报月份"
                type="month"
                value={month}
                onChange={(event) => setMonth(event.target.value)}
                className="block p-2"
                id={`${fieldId}-edition-catalogue-field-1`}
              />
            </Field>
            <Button
              variant="outline"
              disabled={busy || !/^\d{4}-\d{2}$/.test(month)}
              onClick={() => void loadMonth()}
            >
              读取月份
            </Button>
          </div>
          {calendar ? <DailyCalendar calendar={calendar} /> : null}
        </section>
      ) : null}
      {!entries.length ? (
        <p className="text-muted-foreground text-sm">
          当前还没有可公开的{labels[initial.kind]}。
        </p>
      ) : (
        <ol className="divide-y">
          {entries.map((entry) => (
            <li key={entry.key} className="py-5">
              <p className="text-muted-foreground mb-2 text-xs">
                {entry.key} · 修订 {entry.revision} ·{" "}
                {publicationTime(entry.created_at)}
              </p>
              <Link
                href={entry.reading_url}
                className="font-medium underline underline-offset-4"
              >
                {entry.title}
              </Link>
            </li>
          ))}
        </ol>
      )}
      {next ? (
        <Button variant="outline" disabled={busy} onClick={() => void more()}>
          {busy ? "正在读取…" : "更早刊期"}
        </Button>
      ) : null}
    </div>
  );
}

export function DailyCalendar({
  calendar,
}: {
  calendar: HotKeyAPI.PublicDailyCalendarView;
}) {
  const [year, month] = calendar.month.split("-").map(Number);
  const first = new Date(Date.UTC(year, month - 1, 1)).getUTCDay();
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const entries = new Map(
    calendar.entries.map((entry) => [Number(entry.key.slice(-2)), entry]),
  );
  return (
    <div
      className="grid grid-cols-7 gap-2 text-center text-sm"
      aria-label={`${calendar.month} 已公开日报`}
    >
      {["日", "一", "二", "三", "四", "五", "六"].map((label) => (
        <span key={label} className="text-muted-foreground py-1">
          {label}
        </span>
      ))}
      {Array.from({ length: first }, (_, i) => (
        <span key={`blank${i}`} aria-hidden />
      ))}
      {Array.from({ length: days }, (_, i) => {
        const day = i + 1,
          entry = entries.get(day);
        return entry ? (
          <Link
            key={day}
            href={entry.reading_url}
            title={entry.title}
            aria-label={`${entry.key} 日报：${entry.title}`}
            className="bg-secondary rounded-md p-2 underline"
          >
            {day}
          </Link>
        ) : (
          <span
            key={day}
            className="text-muted-foreground/60 p-2"
            aria-label={`${calendar.month}-${String(day).padStart(2, "0")} 暂无公开日报`}
          >
            {day}
          </span>
        );
      })}
    </div>
  );
}
