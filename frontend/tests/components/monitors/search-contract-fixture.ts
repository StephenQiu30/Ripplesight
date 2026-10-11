/** Fixed contract fixture, never platform or acceptance evidence. */
export const searchContract: HotKeyAPI.SourceSearchContractView = {
  version: "keyword-search.v1",
  basis: "connection",
  path_label: "测试查询路径",
  query_mode: "seed_queries",
  query_description: "候选查询不保证全部包含条件在上游执行。",
  scope_description: "仅筛选返回的标题与摘要。",
  conditions: [
    {
      condition: "match_any",
      handling: "upstream_and_local",
      explanation: "任意词用于召回候选，再本地精筛。",
    },
    {
      condition: "match_all",
      handling: "local_only",
      explanation: "必含词逐个本地检查。",
    },
    {
      condition: "exclude",
      handling: "local_only",
      explanation: "排除词逐个本地检查。",
    },
    {
      condition: "language",
      handling: "local_only",
      explanation: "语言未知时不满足指定语言。",
    },
    {
      condition: "window",
      handling: "unsupported",
      explanation: "无法提供历史窗口。",
    },
  ],
  limitations: ["候选不等于全平台覆盖。"],
};

const entry: HotKeyAPI.SourceEntryPointView = {
  status: "pending_verification",
  last_checked_at: null,
  last_persisted_success_at: null,
  stop_reason: null,
  next_action: "待真实验证",
};

export const searchPlatform: HotKeyAPI.SourcePlatformView = {
  source_key: "hackernews",
  display_name: "Hacker News",
  rollout_role: "required",
  status: "pending_verification",
  connection_version: 7,
  connection_id: "fixture-connection",
  connection_status: "active",
  has_credentials: false,
  credential_configured: false,
  credential_update_available: false,
  allowed_hosts: [],
  search_contract: searchContract,
  capabilities: [
    {
      capability: "search",
      display_name: "搜索",
      manual: entry,
      scheduled: entry,
    },
  ],
};
