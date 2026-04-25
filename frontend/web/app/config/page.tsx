import { listKeywordRules, listMonitoredAccounts, listSources } from "@/lib/api-client";

function formatRows<T extends { id: string; [key: string]: unknown }>(title: string, items: T[]) {
  return (
    <section className="rounded-xl border border-slate-800 p-3">
      <h2 className="mb-2 text-sm font-medium">{title}</h2>
      {items.length === 0 ? (
        <div className="text-sm text-slate-400">暂无数据</div>
      ) : (
        <ul className="space-y-1 text-sm">
          {items.map((item) => (
            <li key={item.id} className="rounded border border-slate-700 px-2 py-1">
              {JSON.stringify(item)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default async function ConfigPage() {
  const [sourcesResp, keywordsResp, accountsResp] = await Promise.all([
    listSources({ page: 1, page_size: 100 }),
    listKeywordRules(),
    listMonitoredAccounts(),
  ]);

  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">配置中心（只读）</h1>
      {formatRows("来源列表", sourcesResp.items)}
      {formatRows("X 关键词", keywordsResp.items)}
      {formatRows("X 监控账号", accountsResp.items)}
    </section>
  );
}
