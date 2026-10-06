"use client";
import * as UI from "@/components/ui/content";

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

import {
  Empty,
  EmptyHeader,
  EmptyDescription,
  EmptyTitle,
} from "@/components/ui/empty";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { PageState } from "@/components/system/page-state";
import { Item, ItemContent, ItemGroup } from "@/components/ui/item";
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
type Failure = { code: string; status?: number };
function failure(error: unknown): Failure {
  return error instanceof ApiRequestError
    ? { code: error.code ?? "publication_read_failed", status: error.status }
    : { code: "publication_read_failed" };
}

export function PublicEditionCatalogue({
  initial,
  initialCalendar,
  initialMonth,
  calendarFailure: initialCalendarFailure,
}: {
  initial: HotKeyAPI.PublicEditionCatalogueView;
  initialCalendar?: HotKeyAPI.PublicDailyCalendarView;
  initialMonth?: string;
  calendarFailure?: Failure;
}) {
  const fieldId = useId();

  const [entries, setEntries] = useState(initial.entries);
  const [next, setNext] = useState(initial.next_before_key);
  const [calendar, setCalendar] = useState(initialCalendar);
  const [month, setMonth] = useState(
    initialCalendar?.month ?? initialMonth ?? "",
  );
  const [busy, setBusy] = useState<"more" | "month" | null>(null);
  const [calendarFailure, setCalendarFailure] = useState(
    initialCalendarFailure,
  );
  const [pageFailure, setPageFailure] = useState<Failure>();
  async function more() {
    if (!next || busy) return;
    setBusy("more");
    setPageFailure(undefined);
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
      setPageFailure(failure(error));
    } finally {
      setBusy(null);
    }
  }
  async function loadMonth() {
    if (busy) return;
    setBusy("month");
    setCalendar(undefined);
    setCalendarFailure(undefined);
    try {
      setCalendar(await getPublicDailyCalendar({ month }));
    } catch (error) {
      if (error instanceof ApiRequestError && error.kind === "cancelled")
        return;
      toast.error("暂时无法读取月份日历，请检查月份或重试。");
      setCalendarFailure(failure(error));
    } finally {
      setBusy(null);
    }
  }
  return (
    <UI.Content className="flex min-w-0 flex-col gap-8">
      <UI.Heading level={1}>{labels[initial.kind]}历史</UI.Heading>
      <NavigationMenu
        viewport={false}
        className="max-w-full justify-start print:hidden"
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
      <UI.Content className="grid min-w-0 grid-cols-1 items-start gap-10 lg:grid-cols-3 print:block">
        <UI.Content className="flex min-w-0 flex-col gap-6 lg:col-span-2">
          {!entries.length ? (
            <Empty>
              <EmptyHeader>
                <EmptyTitle>暂无刊物</EmptyTitle>
                <EmptyDescription>
                  当前还没有可公开的{labels[initial.kind]}。
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ItemGroup className="gap-0">
              {entries.map((entry) => (
                <UI.Content key={entry.key}>
                  <Separator />
                  <Item role="listitem" variant="default" className="px-0 py-5">
                    <ItemContent className="min-w-0 gap-3">
                      <UI.Text tone="muted" size="xs">
                        <UI.InlineCode>
                          {entry.key} · 修订 {entry.revision}
                        </UI.InlineCode>{" "}
                        ·{" "}
                        <UI.Timestamp dateTime={entry.created_at}>
                          <UI.InlineCode>
                            {publicationTime(entry.created_at)}
                          </UI.InlineCode>
                        </UI.Timestamp>
                      </UI.Text>
                      <UI.Heading level={2} className="break-words">
                        <UI.TextLink href={entry.reading_url}>
                          {entry.title}
                        </UI.TextLink>
                      </UI.Heading>
                    </ItemContent>
                  </Item>
                </UI.Content>
              ))}
            </ItemGroup>
          )}
          {pageFailure ? (
            <PageState
              state="stale"
              eyebrow="刊物历史"
              title="刊物历史未能更新"
              description="当前列表已过期，更早刊期未能读取；请重试。"
              errorCode={pageFailure.code}
              httpStatus={pageFailure.status}
              action={
                <Button
                  variant="outline"
                  disabled={Boolean(busy)}
                  onClick={() => void more()}
                >
                  重试更早刊期
                </Button>
              }
            />
          ) : null}
          {next ? (
            <Button
              variant="outline"
              disabled={Boolean(busy)}
              aria-busy={busy === "more"}
              onClick={() => void more()}
              className="self-start print:hidden"
            >
              {busy === "more" ? "正在读取…" : "更早刊期"}
            </Button>
          ) : null}
        </UI.Content>
        <UI.Content
          as="aside"
          aria-label="刊物历史工具"
          className="flex min-w-0 flex-col gap-8 print:hidden"
        >
          {initial.kind === "daily" ? (
            <UI.Content
              as="section"
              aria-label="日报月份日历"
              className="flex min-w-0 flex-col gap-4"
            >
              <UI.Heading level={2}>月份日历</UI.Heading>
              <UI.Content className="flex flex-wrap items-end gap-3">
                <Field className="min-w-0 flex-1">
                  <FieldLabel htmlFor={`${fieldId}-edition-catalogue-field-1`}>
                    月份
                  </FieldLabel>
                  <Input
                    aria-label="日报月份"
                    type="month"
                    value={month}
                    disabled={Boolean(busy)}
                    onChange={(event) => setMonth(event.target.value)}
                    id={`${fieldId}-edition-catalogue-field-1`}
                  />
                </Field>
                <Button
                  variant="outline"
                  disabled={Boolean(busy) || !/^\d{4}-\d{2}$/.test(month)}
                  aria-busy={busy === "month"}
                  onClick={() => void loadMonth()}
                >
                  {busy === "month" ? "正在读取月份…" : "读取月份"}
                </Button>
              </UI.Content>
              {busy === "month" ? (
                <PageState
                  state="loading"
                  eyebrow="月份日历"
                  title="正在读取月份日历"
                  description="仅显示真实可读的日报刊期。"
                />
              ) : null}
              {calendarFailure ? (
                <Alert>
                  <AlertTitle>月份日历暂不可用</AlertTitle>
                  <AlertDescription>
                    <UI.Text>请选择月份后重新读取，刊期列表仍可阅读。</UI.Text>
                    <UI.InlineCode>
                      {calendarFailure.code}
                      {calendarFailure.status
                        ? ` · ${calendarFailure.status}`
                        : ""}
                    </UI.InlineCode>
                  </AlertDescription>
                </Alert>
              ) : null}
              {calendar ? <DailyCalendar calendar={calendar} /> : null}
            </UI.Content>
          ) : null}
          <UI.Content className="flex flex-col gap-3">
            <UI.Heading level={2}>订阅{labels[initial.kind]}</UI.Heading>
            <Button asChild variant="outline">
              <UI.TextLink href={`/feed/${initial.kind}.xml`}>
                订阅{labels[initial.kind]}
              </UI.TextLink>
            </Button>
          </UI.Content>
        </UI.Content>
      </UI.Content>
    </UI.Content>
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
