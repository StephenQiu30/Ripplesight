import { cn } from "@/lib/utils";

/** Unknown observations retain their place in the design without inventing a series. */
export function ObservationGap({
  children,
  compact = false,
}: {
  children: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <div
      role="note"
      className={cn(
        "text-muted-foreground flex items-center justify-center text-xs leading-5",
        compact
          ? "h-8"
          : "bg-muted/50 h-48 rounded-lg border-b px-6 text-center",
      )}
    >
      {children}
    </div>
  );
}

export function SentimentLegend() {
  return (
    <div
      aria-label="情感图例"
      className="text-muted-foreground flex shrink-0 items-center gap-3 text-xs"
    >
      <span className="flex items-center gap-1.5">
        <span aria-hidden="true" className="bg-foreground h-1 w-2.5" />
        正面
      </span>
      <span className="flex items-center gap-1.5">
        <span aria-hidden="true" className="bg-border h-1 w-2.5" />
        中性
      </span>
      <span className="flex items-center gap-1.5">
        <span aria-hidden="true" className="bg-destructive h-1 w-2.5" />
        负面
      </span>
    </div>
  );
}

export function SignalNotice({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      aria-label={title}
      className="bg-muted flex flex-col gap-3 rounded-xl p-5 text-sm leading-6"
    >
      <h2 className="text-destructive flex items-center gap-2 text-xs font-semibold">
        <span
          aria-hidden="true"
          className="bg-destructive size-1.5 rounded-full"
        />
        {title}
      </h2>
      {children}
    </section>
  );
}
