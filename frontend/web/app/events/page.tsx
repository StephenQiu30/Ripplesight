import Link from "next/link";
import { EventCard } from "@/components/EventCard";
import { HotspotEvent, listEvents } from "@/lib/api-client";

type SearchParams = {
  page?: string;
  page_size?: string;
  topic?: string;
  source_type?: string;
  from_date?: string;
  to_date?: string;
};

type Props = {
  searchParams: SearchParams;
};

function buildQuery(params: {
  page?: number;
  pageSize?: number;
  topic?: string;
  sourceType?: string;
}) {
  const next = new URLSearchParams();
  if (params.page && params.page > 1) next.set("page", String(params.page));
  if (params.pageSize && params.pageSize !== 20) next.set("page_size", String(params.pageSize));
  if (params.topic) next.set("topic", params.topic);
  if (params.sourceType) next.set("source_type", params.sourceType);
  return next;
}

export default async function EventsPage({ searchParams }: Props) {
  const page = Math.max(1, Number(searchParams.page ?? 1));
  const pageSize = Math.max(1, Math.min(100, Number(searchParams.page_size ?? 20)));
  const topic = searchParams.topic?.trim();
  const sourceType = searchParams.source_type?.trim();

  let payload: Awaited<ReturnType<typeof listEvents>> | null = null;
  let errorMessage: string | null = null;

  try {
    payload = await listEvents({
      page,
      page_size: pageSize,
      topic,
      source_type: sourceType,
    });
  } catch (error) {
    errorMessage = error instanceof Error ? error.message : "请求失败";
  }

  if (!payload) {
    payload = { items: [], meta: { page, page_size: pageSize, total: 0 } };
  }

  const maxPage = Math.max(1, Math.ceil(payload.meta.total / pageSize));
  const hasPrev = page > 1;
  const hasNext = page < maxPage;

  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">今日热点榜</h1>
      <form method="get" className="mb-4 grid gap-2 md:grid-cols-4">
        <label className="text-sm">
          关键词
          <input
            name="topic"
            defaultValue={topic}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 p-2"
            placeholder="例如：reasoning"
          />
        </label>
        <label className="text-sm">
          来源类型
          <input
            name="source_type"
            defaultValue={sourceType}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 p-2"
            placeholder="例如：x / news"
          />
        </label>
        <label className="text-sm">
          每页
          <input name="page_size" defaultValue={pageSize} type="number" min={1} max={100} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 p-2" />
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-600"
          >
            查询
          </button>
        </div>
      </form>
      {errorMessage ? <div className="error mb-3 rounded-lg p-3 text-sm">查询失败：{errorMessage}</div> : null}
      <div className="space-y-3">
        {payload.items.map((event: HotspotEvent) => (
          <EventCard key={event.id} event={event} />
        ))}
        {payload.items.length === 0 ? <div className="rounded-xl border border-slate-800 p-4 text-sm text-slate-300">暂无热点数据</div> : null}
      </div>
      <div className="mt-4 flex items-center gap-2">
        {hasPrev ? (
          <Link
            href={`/events?${buildQuery({ page: page - 1, pageSize, topic, sourceType }).toString()}`}
            className="rounded border border-slate-700 px-3 py-1 text-sm"
          >
            上一页
          </Link>
        ) : null}
        <span className="text-sm text-slate-300">
          第 {payload.meta.page}/{maxPage} 页
        </span>
        {hasNext ? (
          <Link
            href={`/events?${buildQuery({ page: page + 1, pageSize, topic, sourceType }).toString()}`}
            className="rounded border border-slate-700 px-3 py-1 text-sm"
          >
            下一页
          </Link>
        ) : null}
      </div>
    </section>
  );
}
