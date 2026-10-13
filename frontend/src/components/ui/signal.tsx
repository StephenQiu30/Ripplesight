import { cn } from "@/lib/utils";
import { Alert, AlertTitle, AlertDescription } from "./alert";

/** Unknown observations retain their place in the design without inventing a series. */
export function ObservationGap({
  children,
  compact = false,
  size = "default",
}: {
  children: React.ReactNode;
  compact?: boolean;
  size?: "default" | "hourly";
}) {
  return (
    <div
      role="note"
      className={cn(
        "text-muted-foreground flex items-center justify-center text-xs leading-5",
        compact
          ? "h-8"
          : "bg-muted/50 h-48 rounded-lg border-b px-6 text-center",
        !compact && size === "hourly" && "h-35",
      )}
    >
      {children}
    </div>
  );
}

export function SentimentLegend() {
  return (
    <div
      role="group"
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
    <Alert variant="signal" role="note" aria-label={title}>
      <AlertTitle className="text-destructive flex items-center gap-2 text-xs font-semibold">
        <span
          aria-hidden="true"
          className="bg-destructive size-1.5 rounded-full"
        />
        {title}
      </AlertTitle>
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  );
}
