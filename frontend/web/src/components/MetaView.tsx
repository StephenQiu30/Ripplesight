type MetaViewProps = {
  label: string;
  value: string | number;
};

export function MetaView({ label, value }: MetaViewProps) {
  return (
    <div className="rounded-xl border border-slate-800 p-2 text-sm">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-slate-100">{value}</div>
    </div>
  );
}
