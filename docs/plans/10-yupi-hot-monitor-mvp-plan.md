# 10 Yupi Hot Monitor MVP Migration Plan

## 目标

将鱼皮 `yupi-hot-monitor` 的 MVP 功能闭环迁移到本项目当前技术栈中。

本项目不复制鱼皮项目的 `Express + React + Prisma + SQLite` 技术栈，而是继续使用 `Python + FastAPI + PostgreSQL + SQLAlchemy + Next.js`。

## 范围

- 关键词监控。
- 多源聚合抓取。
- AI 查询扩展。
- AI 真假识别、相关性评分、重要性判断和中文摘要。
- 阈值过滤。
- 热点事件邮件通知。
- AI 日报邮件通知。
- 全网搜索接口。

## 数据源

P0 迁移以下来源能力：

- RSS
- Hacker News
- X/Twitter，使用官方 X API v2 Recent Search
- Bing Search
- Bilibili
- Sogou-style public search

所有来源必须统一输出候选结构：标题、URL、来源、作者、发布时间、摘要、原始 payload、关键词 ID。

## 实现步骤

1. 保留现有 RSS 和 Hacker News adapter。
2. 新增 X/Twitter adapter，凭据通过 `X_API_BEARER_TOKEN` 注入。
3. 新增 Bing adapter，凭据通过 `BING_SEARCH_API_KEY` 注入。
4. 新增 Bilibili 和 Sogou-style best-effort adapter。
5. 为关键词增加 AI 查询扩展，生成 2-5 个相关查询。
6. 对候选热点执行 AI 分析，输出真实性、相关性、关键词命中、重要性和中文摘要。
7. 低于 `RELEVANCE_THRESHOLD` 的热点标记为 `filtered`。
8. 达到 `RELEVANCE_THRESHOLD` 的热点标记为 `active`。
9. 仅 `active` 热点发送事件邮件。
10. AI 日报仅聚合 `active` 热点。
11. 新增 `/api/search` 即时全网搜索接口。

## 验收标准

- X/Twitter 未配置 Token 时，系统跳过该来源且不影响其他来源。
- Bing 未配置 Key 时，系统跳过该来源且不影响其他来源。
- 单个来源失败不会中断整体热点检查。
- AI 查询扩展能为关键词生成 2-5 个查询。
- 低相关热点不会发送事件邮件，也不会进入日报。
- 高相关热点可以进入热点列表、事件邮件和日报。
- `/api/search` 可以返回跨源分析结果和来源错误信息。

## 非目标

- 不迁移鱼皮项目技术栈。
- 不引入 Redis、Celery、复杂队列或向量库。
- 不做多用户、多租户、权限或计费。
- 不把页面爬取作为 X/Twitter 默认实现。
