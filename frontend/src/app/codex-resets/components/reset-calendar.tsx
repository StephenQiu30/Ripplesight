"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

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
  const [month, setMonth] = useState(snapshot.today.slice(0, 7));
  const [year, number] = month.split("-").map(Number);
  const first = new Date(Date.UTC(year, number - 1, 1));
  const offset = (first.getUTCDay() + 6) % 7;
  const count = new Date(Date.UTC(year, number, 0)).getUTCDate();
  const marks = snapshot.calendar.filter((mark) => mark.date.startsWith(month));
  function changeMonth(delta: number) {
    setMonth(
      new Date(Date.UTC(year, number - 1 + delta, 1)).toISOString().slice(0, 7),
    );
    onSelect(null);
  }
  return (
    <section
      aria-label="重置公告日历"
      className="bg-muted/40 rounded-2xl p-5 sm:p-6"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-medium">
          {year} 年 {number} 月
        </h2>
        <div className="flex gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label="上个月"
            onClick={() => changeMonth(-1)}
          >
            <ChevronLeftIcon />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="下个月"
            onClick={() => changeMonth(1)}
          >
            <ChevronRightIcon />
          </Button>
        </div>
      </div>
      <p className="text-muted-foreground mt-2 text-sm">
        日期按北京时间。推测状态不表示已确认到账。
      </p>
      <div className="mt-6 grid grid-cols-7 gap-1 text-center text-sm">
        {["一", "二", "三", "四", "五", "六", "日"].map((day) => (
          <span key={day} className="text-muted-foreground py-2">
            {day}
          </span>
        ))}
        {Array.from({ length: offset }, (_, index) => (
          <span key={`empty-${index}`} aria-hidden="true" />
        ))}
        {Array.from({ length: count }, (_, index) => {
          const date = `${month}-${String(index + 1).padStart(2, "0")}`;
          const daily = marks.filter((mark) => mark.date === date);
          const label = daily
            .map(
              (mark) =>
                `${mark.kind === "reset_credit" ? "重置额度" : "直接重置"}，${stateLabels[mark.state]}`,
            )
            .join("；");
          return (
            <Button
              key={date}
              type="button"
              aria-label={`${date}${label ? `，${label}` : "，无公告记录"}`}
              aria-pressed={selectedDate === date}
              onClick={() => onSelect(selectedDate === date ? null : date)}
              variant={
                selectedDate === date
                  ? "default"
                  : date === snapshot.today
                    ? "secondary"
                    : "ghost"
              }
              className="h-auto min-h-14 min-w-0 flex-col gap-1 px-0"
            >
              <span>{index + 1}</span>
              <span aria-hidden="true" className="flex min-h-1 gap-1">
                {daily.map((mark) => (
                  <span
                    key={mark.event_id}
                    className={cn(
                      "size-1 rounded-full",
                      mark.state === "confirmed"
                        ? "bg-chart-1"
                        : mark.state === "likely"
                          ? "bg-chart-3"
                          : "bg-muted-foreground",
                    )}
                  />
                ))}
              </span>
            </Button>
          );
        })}
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        {Object.entries(stateLabels).map(([key, label]) => (
          <Badge key={key} variant="secondary">
            {label}
          </Badge>
        ))}
      </div>
      {marks.length === 0 && (
        <p className="text-muted-foreground mt-4 text-sm">
          这个月没有公告记录。
        </p>
      )}
      {selectedDate && (
        <Button variant="ghost" className="mt-3" onClick={() => onSelect(null)}>
          清除日期筛选
        </Button>
      )}
    </section>
  );
}
