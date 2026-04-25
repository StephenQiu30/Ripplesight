import { getTodayDigest } from "@/lib/api-client";
import { MetaView } from "@/components/MetaView";

export default async function DigestPage() {
  const digest = await getTodayDigest();

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">今日热点日报</h1>
      <div className="grid gap-2 md:grid-cols-3">
        <MetaView label="日报日期" value={digest.digest_date} />
        <MetaView label="投递状态" value={digest.delivery_status} />
        <MetaView label="事件数量" value={digest.event_ids.length} />
      </div>
      <div className="rounded-xl border border-slate-800 p-3">
        <h2 className="mb-2 text-sm font-medium">{digest.title}</h2>
        <ul className="list-inside list-disc space-y-1 text-sm">
          {digest.highlights.map((highlight: string) => (
            <li key={highlight}>{highlight}</li>
          ))}
        </ul>
      </div>
      <div className="rounded-xl border border-slate-800 p-3">
        <div className="mb-2 text-sm font-medium">关联事件</div>
        <div className="text-sm text-slate-200">{digest.event_ids.join(", ") || "暂无"}</div>
      </div>
    </section>
  );
}
