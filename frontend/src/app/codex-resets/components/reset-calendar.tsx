"use client";

import { useCallback, useMemo, useState, type ComponentProps } from "react";
import { format } from "date-fns";
import { zhCN } from "react-day-picker/locale";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar, CalendarDayButton } from "@/components/ui/calendar";
import { Empty, EmptyDescription, EmptyHeader } from "@/components/ui/empty";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";

const stateLabels: Record<HotKeyAPI.CalendarMark["state"], string> = {
  confirmed: "已确认",
  likely: "推测已完成",
  pending: "待确认",
};

export function ResetCalendar({
  snapshot,
  selectedDate,
  onSelect,
}: {
  snapshot: HotKeyAPI.ResetSnapshot;
  selectedDate: string | null;
  onSelect: (date: string | null) => void;
}) {
  const [month, setMonth] = useState(
    () => new Date(`${snapshot.today.slice(0, 7)}-01T00:00:00+08:00`),
  );
  const marksByDate = useMemo(() => {
    const entries = new Map<string, HotKeyAPI.CalendarMark[]>();
    for (const mark of snapshot.calendar) {
      const daily = entries.get(mark.date) ?? [];
      daily.push(mark);
      entries.set(mark.date, daily);
    }
    return entries;
  }, [snapshot.calendar]);
  const renderDay = useCallback(
    function MarkedDay({
      day,
      modifiers,
      ...props
    }: ComponentProps<typeof CalendarDayButton>) {
      const date = format(day.date, "yyyy-MM-dd");
      const daily = marksByDate.get(date) ?? [];
      const label = daily
        .map(
          (mark) =>
            `${mark.kind === "reset_credit" ? "重置额度" : "直接重置"}，${stateLabels[mark.state]}`,
        )
        .join("；");
      return (
        <CalendarDayButton
          {...props}
          day={day}
          modifiers={modifiers}
          aria-label={`${date}${label ? `，${label}` : "，无公告记录"}`}
          className="aspect-auto min-h-11 min-w-0 sm:min-h-14"
        >
          {day.date.getDate()}
          <span aria-hidden="true" className="flex min-h-1.5 gap-1">
            {daily.map((mark) => (
              <Badge
                key={mark.event_id}
                variant={
                  mark.state === "confirmed"
                    ? "default"
                    : mark.state === "likely"
                      ? "secondary"
                      : "outline"
                }
                className="size-1.5 p-0"
              >
                <span className="sr-only">{stateLabels[mark.state]}</span>
              </Badge>
            ))}
          </span>
        </CalendarDayButton>
      );
    },
    [marksByDate],
  );
  const monthKey = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
  }).format(month);
  const marks = snapshot.calendar.filter((mark) =>
    mark.date.startsWith(monthKey),
  );
  return (
    <Item variant="muted" asChild>
      <section aria-label="重置公告日历" className="min-w-0 p-5 sm:p-6">
        <ItemContent className="min-w-0 gap-4">
          <ItemTitle>
            <h2>重置公告日历</h2>
          </ItemTitle>
          <ItemDescription className="line-clamp-none">
            日期按北京时间。推测状态不表示已确认到账。
          </ItemDescription>
          <Calendar
            mode="single"
            locale={zhCN}
            timeZone="Asia/Shanghai"
            weekStartsOn={1}
            month={month}
            today={new Date(`${snapshot.today}T00:00:00+08:00`)}
            selected={
              selectedDate
                ? new Date(`${selectedDate}T00:00:00+08:00`)
                : undefined
            }
            onSelect={(date) =>
              onSelect(date ? format(date, "yyyy-MM-dd") : null)
            }
            onMonthChange={(value) => {
              setMonth(value);
              onSelect(null);
            }}
            showOutsideDays={false}
            className="w-full"
            labels={{
              labelPrevious: () => "上个月",
              labelNext: () => "下个月",
            }}
            components={{ DayButton: renderDay }}
          />
          <div className="flex flex-wrap gap-2">
            {Object.entries(stateLabels).map(([key, label]) => (
              <Badge
                key={key}
                variant={
                  key === "confirmed"
                    ? "default"
                    : key === "likely"
                      ? "secondary"
                      : "outline"
                }
              >
                {label}
              </Badge>
            ))}
          </div>
          {marks.length === 0 && (
            <Empty>
              <EmptyHeader>
                <EmptyDescription>这个月没有公告记录。</EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
          {selectedDate && (
            <Button variant="ghost" onClick={() => onSelect(null)}>
              清除日期筛选
            </Button>
          )}
        </ItemContent>
      </section>
    </Item>
  );
}
