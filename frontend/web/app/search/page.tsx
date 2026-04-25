import Link from "next/link";
import { EventCard } from "@/components/EventCard";
import { searchEvents, type HotspotEvent, type PaginatedResponse } from "@/lib/api-client";

type SearchParams = {
  q?: string;
  page?: string;
  page_size?: string;
};

type Props = {
  searchParams: SearchParams;
};

function buildQuery(q: string, page: number, pageSize: number) {
  const params = new URLSearchParams();
  params.set("q", q);
  if (page > 1) params.set("page", String(page));
  if (pageSize !== 20) params.set("page_size", String(pageSize));
  return params;
}

export default async function SearchPage({ searchParams }: Props) {
  const q = searchParams.q?.trim() || "";
  const page = Math.max(1, Number(searchParams.page ?? 1));
  const pageSize = Math.max(1, Math.min(100, Number(searchParams.page_size ?? 20)));
  let result: PaginatedResponse<HotspotEvent> = {
    items: [],
    meta: { page: 1, page_size: pageSize, total: 0 },
  };
  let errorMessage = "";

  if (q) {
    try {
      result = await searchEvents({ q, page, page_size: pageSize });
    } catch (error) {
      errorMessage = error instanceof Error ? error.message : "搜索失败";
    }
  }

  const totalPage = Math.max(1, Math.ceil(result.meta.total / pageSize));
  const hasPrev = page > 1;
  const hasNext = page < totalPage;

  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">搜索热点</h1>
      <form method="get" className="mb-4 flex gap-2">
        <input
          name="q"
          defaultValue={q}
          className="flex-1 rounded-lg border border-slate-700 bg-slate-950 p-2 text-sm"
          placeholder="输入关键词，例如：AI、R1、OpenAI"
        />
        <button type="submit" className="rounded-lg bg-cyan-700 px-3 py-2 text-sm text-white">
          搜索
        </button>
      </form>
      {errorMessage ? <div className="error mb-3 rounded p-2 text-sm">{errorMessage}</div> : null}
      {!q ? <div className="text-sm text-slate-300">请输入关键词执行搜索</div> : null}
      {q ? (
        <>
          <div className="space-y-3">
            {result.items.map((item: HotspotEvent) => (
              <EventCard key={item.id} event={item} />
            ))}
            {result.items.length === 0 ? <div className="rounded-xl border border-slate-800 p-4 text-sm text-slate-300">未搜索到结果</div> : null}
          </div>
          <div className="mt-4 flex items-center gap-2">
            {hasPrev ? (
              <Link
                href={`/search?${buildQuery(q, page - 1, pageSize).toString()}`}
                className="rounded border border-slate-700 px-3 py-1 text-sm"
              >
                上一页
              </Link>
            ) : null}
            <span className="text-sm text-slate-300">
              第 {result.meta.page}/{totalPage} 页
            </span>
            {hasNext ? (
              <Link
                href={`/search?${buildQuery(q, page + 1, pageSize).toString()}`}
                className="rounded border border-slate-700 px-3 py-1 text-sm"
              >
                下一页
              </Link>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
