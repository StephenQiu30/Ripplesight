"use client";
import { format } from "date-fns";
import { zhCN } from "react-day-picker/locale";
import { Calendar } from "@/components/ui/calendar";
import { TableCell } from "@/components/ui/table";
import {
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuLink,
} from "@/components/ui/navigation-menu";

import { Empty, EmptyHeader, EmptyDescription } from "@/components/ui/empty";
import {
  Item,
  ItemContent,
  ItemGroup,
  ItemTitle,
  ItemDescription,
} from "@/components/ui/item";
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
      <NavigationMenu
        viewport={false}
        className="max-w-full justify-start"
        aria-label="公开刊物"
      >
        <NavigationMenuList className="flex-wrap justify-start gap-2">
          {(["daily", "weekly", "monthly"] as const).map((kind) => (
            <NavigationMenuItem key={kind}>
              <NavigationMenuLink asChild active={kind === initial.kind}>
                <Link
                  href={`/reports/${kind}/archive`}
                  aria-current={kind === initial.kind ? "page" : undefined}
                >
                  {labels[kind]}历史
                </Link>
              </NavigationMenuLink>
            </NavigationMenuItem>
          ))}
          <NavigationMenuItem>
            <NavigationMenuLink asChild>
              <Link href={`/reports/${initial.kind}`}>
                最新{labels[initial.kind]}
              </Link>
            </NavigationMenuLink>
          </NavigationMenuItem>
        </NavigationMenuList>
      </NavigationMenu>
      {initial.kind === "daily" ? (
        <Item variant="outline" asChild>
          <section
            aria-label="日报月份日历"
            className="flex flex-col gap-y-4 p-5"
          >
            <ItemContent className="min-w-0 gap-3">
              <ItemTitle className="line-clamp-none w-full">
                <h2>月份日历</h2>
              </ItemTitle>
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
            </ItemContent>
          </section>
        </Item>
      ) : null}
      {!entries.length ? (
        <Empty>
          <EmptyHeader>
            <EmptyDescription>
              当前还没有可公开的{labels[initial.kind]}。
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <ItemGroup className="">
          {entries.map((entry) => (
            <Item
              role="listitem"
              variant="default"
              key={entry.key}
              className="py-5"
            >
              <ItemContent className="min-w-0 gap-3">
                <ItemDescription className="mb-2 line-clamp-none">
                  {entry.key} · 修订 {entry.revision} ·{" "}
                  {publicationTime(entry.created_at)}
                </ItemDescription>
                <Link
                  href={entry.reading_url}
                  className="font-medium underline underline-offset-4"
                >
                  {entry.title}
                </Link>
              </ItemContent>
            </Item>
          ))}
        </ItemGroup>
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
  const entries = new Map(calendar.entries.map((entry) => [entry.key, entry]));
  return (
    <Calendar
      locale={zhCN}
      timeZone="Asia/Shanghai"
      weekStartsOn={0}
      month={new Date(`${calendar.month}-01T00:00:00+08:00`)}
      hideNavigation
      showOutsideDays={false}
      className="w-full"
      aria-label={`${calendar.month} 已公开日报`}
      components={{
        Day: ({ day, modifiers, children, ...props }) => {
          const key = format(day.date, "yyyy-MM-dd");
          const entry = entries.get(key);
          return (
            <TableCell {...props}>
              {modifiers.hidden ? null : entry ? (
                <Button
                  asChild
                  variant="secondary"
                  className="size-full min-w-0 px-0"
                >
                  <Link
                    href={entry.reading_url}
                    title={entry.title}
                    aria-label={`${entry.key} 日报：${entry.title}`}
                  >
                    {children}
                  </Link>
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  disabled
                  className="size-full min-w-0 px-0"
                  aria-label={`${key} 暂无公开日报`}
                >
                  {children}
                </Button>
              )}
            </TableCell>
          );
        },
      }}
    />
  );
}
