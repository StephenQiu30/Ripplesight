# 11 Backend Hotspot Detection and Reports Plan

## 目标

当前阶段优先跑通后端 AI 热点检测、即时搜索、日报/周报生成闭环。

MVP 阶段暂不实现控制台功能，不做过度设计；后续实现以可运行、可配置、失败可追踪为优先。

## 当前范围

- 后端 AI 热点检测主链路。
- `/api/search` 即时搜索。
- 统一日报/周报报告能力。
- SMTP 报告发送和通知状态记录。
- 后端测试与可验收用例。

## 非目标

- 不实现控制台页面。
- 不做登录、权限、多租户或计费。
- 不引入 Celery、Redis、向量库或复杂任务平台。
- 不做复杂报告模板系统。
- 不保留 `/api/daily-reports` 兼容别名。

## 热点检测实现计划

1. 补强 `POST /api/check-runs` 触发的热点检测主链路。
2. 手动触发和定时触发继续复用同一条业务编排。
3. 每次任务加载启用关键词和启用来源；必要时写入默认来源定义。
4. 每个关键词执行 AI 查询扩展，生成 2-5 个查询词。
5. 每个来源 adapter 输出统一 `Candidate` 结构。
6. 单个来源失败只记录到任务错误摘要，不中断整体任务。
7. 按 `source_id + url` 去重入库；重复候选不重复分析、不重复通知。
8. 对新热点执行 AI 分析，输出真实性、相关性、理由、关键词命中、重要性和摘要。
9. `relevance_score >= RELEVANCE_THRESHOLD` 且 `is_real is not False` 的热点标记为 `active`。
10. 其他热点标记为 `filtered`。
11. 只有 `active` 热点允许发送事件邮件和进入日报/周报。

## 即时搜索实现计划

1. 保留 `POST /api/search` 作为即时搜索入口。
2. 搜索复用查询扩展、来源 adapter 和 AI 分析能力。
3. 搜索结果不入库、不发送事件邮件、不影响日报/周报。
4. 返回搜索结果列表和来源错误列表。
5. 结果按重要性等级和相关性分数排序。
6. 空库首次搜索时也应确保默认来源存在。
7. RSS 可作为 feed 型来源；Hacker News 后续优先改为 query-capable 搜索实现。

## 日报/周报实现计划

1. 将现有 `daily_reports` 泛化为统一 `reports`。
2. `/api/daily-reports` 后续直接删除，不做兼容别名。
3. 报告支持 `daily` 和 `weekly` 两种 `report_type`。
4. 日报周期为某一天 00:00:00 到次日 00:00:00。
5. 周报周期为 ISO 周一 00:00:00 到下周一 00:00:00。
6. 手动日报默认生成当天；定时日报默认生成昨天。
7. 手动周报默认生成当前 ISO 周；定时周报默认生成上一完整 ISO 周。
8. 报告只聚合周期内 `active` 热点。
9. `filtered` 热点不得进入报告。
10. 日报最多取 Top 10，周报最多取 Top 20。
11. 排序规则为重要性等级、相关性分数、抓取时间。
12. 报告内容模板优先生成 Markdown；AI 只作为可选增强。
13. AI 未配置或失败时必须使用本地模板生成报告。
14. 无热点时仍生成空报告，并说明该周期无符合阈值热点。

## API 范围

保留以下后端 API：

- `POST /api/check-runs`
- `GET /api/check-runs`
- `GET /api/check-runs/{id}`
- `POST /api/search`
- `GET /api/hotspots`
- `GET /api/hotspots/{id}`

新增以下报告 API：

- `POST /api/reports`
- `GET /api/reports`
- `GET /api/reports/{id}`
- `POST /api/reports/{id}/send`

删除以下旧日报 API，不保留兼容别名：

- `POST /api/daily-reports`
- `GET /api/daily-reports`
- `GET /api/daily-reports/{id}`
- `POST /api/daily-reports/{report_id}/send`

## 数据模型调整

- 将 `daily_reports` 替换为统一 `reports`。
- `reports` 至少包含 `report_type`、`period_start`、`period_end`、`status`、`subject`、`summary`、`content`、`hotspot_count`、`sent_at`。
- `report_type` 仅支持 `daily` 和 `weekly`。
- `report_type + period_start + period_end` 必须唯一。
- `notifications` 后续关联 `report_id`，不再使用 `daily_report_id`。
- MVP 允许重建 schema，不做旧数据迁移。

## 降级与失败处理

- AI 查询扩展失败时使用本地查询扩展。
- AI 分析失败时使用本地分析 fallback，并记录可追踪信息。
- 报告 AI 增强失败时使用模板报告。
- SMTP 未配置时发送状态记录为 `skipped`，主流程继续。
- SMTP 发送失败时记录 `failed` 和错误信息，热点入库与报告生成不回滚。
- X/Twitter 未配置时跳过该来源。
- Bing 未配置时跳过该来源。

## 测试与验收标准

- 热点检测可以从至少一个关键词和两个来源产生候选。
- 单个来源失败不会中断整体检测任务。
- 同一 `source_id + url` 不会重复入库。
- AI 查询扩展返回 2-5 个去重查询词。
- `active` 和 `filtered` 阈值过滤正确。
- `filtered` 热点不发送事件邮件、不进入日报/周报。
- `/api/search` 返回结果和来源错误，且不创建热点。
- `/api/reports` 可生成 `daily` 和 `weekly` 报告。
- `/api/daily-reports` 不再注册。
- 报告只包含 `active` 热点。
- SMTP 缺失时报告发送记录为 `skipped`。

## 执行顺序

1. 补强热点检测主链路。
2. 补强 `/api/search` 即时搜索。
3. 将 `daily_reports` 泛化为统一 `reports`。
4. 删除 `/api/daily-reports` 相关 route、schema、service、model 命名入口。
5. 新增 `/api/reports` 报告 API。
6. 实现日报/周报生成与发送。
7. 补齐后端测试与验收用例。
