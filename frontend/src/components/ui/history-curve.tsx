import { cn } from "@/lib/utils";

export type CurvePoint = {
  at: string;
  value?: number | null;
  segment?: string | null;
};

/** Fixed hourly points: gaps and changed cohorts never acquire connecting lines. */
export function HistoryCurve({
  points,
  label,
  className,
}: {
  points: CurvePoint[];
  label: string;
  className?: string;
}) {
  const valid = points.flatMap((point) =>
    point.value != null && Number.isFinite(point.value) ? [point.value] : [],
  );
  const max = Math.max(1, ...valid);
  const position = (index: number, value: number) => ({
    x: 4 + (index * 232) / Math.max(1, points.length - 1),
    y: 56 - (value / max) * 48,
  });
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox="0 0 240 64"
      className={cn("text-foreground h-16 w-full", className)}
    >
      <title>{label}</title>
      {points.map((point, index) => {
        if (point.value == null || !Number.isFinite(point.value)) return null;
        const current = position(index, point.value);
        const previous = points[index - 1];
        const connect =
          previous?.value != null &&
          Number.isFinite(previous.value) &&
          point.segment != null &&
          previous.segment === point.segment &&
          Date.parse(point.at) - Date.parse(previous.at) === 3600000;
        const start = connect ? position(index - 1, previous.value!) : null;
        return (
          <g key={point.at}>
            {start ? (
              <line
                x1={start.x}
                y1={start.y}
                x2={current.x}
                y2={current.y}
                stroke="currentColor"
                strokeWidth="1.5"
              />
            ) : null}
            <circle cx={current.x} cy={current.y} r="1.5" fill="currentColor" />
          </g>
        );
      })}
    </svg>
  );
}
