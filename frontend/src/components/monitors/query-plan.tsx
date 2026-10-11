import * as UI from "@/components/ui/content";

const REASONS = {
  query_limit: "查询上限",
  source_unavailable: "来源待就绪",
  quiet: "静默时段",
  budget: "预算不足",
  rate_limited: "来源间隔尚未到期",
} as const;

export function QueryPlan({
  plan,
}: {
  plan: HotKeyAPI.KeywordQueryPlanView | null | undefined;
}) {
  if (!plan) {
    return (
      <UI.Text tone="muted" size="sm">
        此次运行未保存逐查询受理记录。
      </UI.Text>
    );
  }
  return (
    <UI.Content
      className="flex min-w-0 flex-col gap-2"
      aria-label="查询受理范围"
    >
      {plan.collection ? (
        <UI.Content className="flex min-w-0 flex-col gap-1">
          <UI.Text size="sm">
            冻结配置：
            {plan.collection.topic.search_language === "any"
              ? "不限语言"
              : `${plan.collection.topic.search_language}（本地元数据筛选，未知排除）`}
            ；主题窗口 {plan.collection.topic.search_window_seconds} 秒。
          </UI.Text>
          <UI.Text size="sm" className="break-words">
            实际窗口：{plan.collection.starts_at} 至 {plan.collection.ends_at}
            （UTC，右端不含）。
          </UI.Text>
          <UI.Text size="sm">
            有效上限：每来源 {plan.max_queries} 个查询；每查询{" "}
            {plan.collection.max_items_per_query} 条候选、每轮{" "}
            {plan.collection.max_requests_per_query} 次平台请求。主题上限：
            {plan.collection.topic.max_queries} /{" "}
            {plan.collection.topic.max_items_per_query} /{" "}
            {plan.collection.topic.max_requests_per_query}。
          </UI.Text>
          <UI.Text tone="muted" size="sm">
            语言未知和发布时间未知不证明命中指定范围；达到上限不表示已完整采集。
          </UI.Text>
        </UI.Content>
      ) : (
        <UI.Text tone="muted" size="sm">
          此次运行未保存主题采集配置。
        </UI.Text>
      )}
      {plan.queries.map((query) => (
        <UI.Text key={query.query_index} size="sm" className="break-words">
          <UI.InlineCode>{query.query}</UI.InlineCode>
          {"："}
          {query.admitted
            ? "已受理"
            : `未受理（${query.skip_reason ? REASONS[query.skip_reason] : "原因未提供"}${query.skip_reason === "query_limit" ? ` ${plan.max_queries} 项` : ""}）`}
        </UI.Text>
      ))}
      <UI.Text tone="muted" size="sm">
        受理不表示已发起请求或完成采集；未受理查询不计为零结果。
      </UI.Text>
    </UI.Content>
  );
}
