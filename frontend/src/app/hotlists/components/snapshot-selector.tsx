"use client";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function formatHotlistTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

type SnapshotSelectorProps = {
  snapshots: HotKeyAPI.HotlistSnapshotSummaryView[];
  selectedId: string;
  nextCursor: string | null;
  loadingMore: boolean;
  onSelect: (snapshotId: string) => void;
  onLoadMore: () => void;
};

export function SnapshotSelector({
  snapshots,
  selectedId,
  nextCursor,
  loadingMore,
  onSelect,
  onLoadMore,
}: SnapshotSelectorProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="min-w-56 flex-1 sm:flex-none">
        <label
          className="text-muted-foreground mb-2 block text-sm"
          htmlFor="snapshot-select"
        >
          观察时间
        </label>
        <Select value={selectedId} onValueChange={onSelect}>
          <SelectTrigger id="snapshot-select" className="h-11 w-full">
            <SelectValue placeholder="选择历史快照" />
          </SelectTrigger>
          <SelectContent>
            {snapshots.map((snapshot) => (
              <SelectItem
                key={snapshot.snapshot_id}
                value={snapshot.snapshot_id}
              >
                {formatHotlistTime(snapshot.observed_at)} ·{" "}
                {snapshot.entry_count} 条
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {nextCursor ? (
        <Button
          type="button"
          variant="secondary"
          onClick={onLoadMore}
          disabled={loadingMore}
        >
          {loadingMore ? "正在加载" : "更多时间"}
        </Button>
      ) : null}
    </div>
  );
}
