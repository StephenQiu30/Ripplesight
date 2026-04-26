# AI 热点监控工具执行计划导航

本项目从零重建。旧实现、旧目录结构、旧数据库结构、旧 OpenAPI 契约和旧示例数据均不保留。

后续实现以 `docs/plans/` 下的计划文件为准，每个计划文件都是一个可独立执行和验收的任务单。

## 执行顺序

1. [00-foundation-plan.md](../plans/00-foundation-plan.md)
2. [01-keyword-plan.md](../plans/01-keyword-plan.md)
3. [02-source-ingestion-plan.md](../plans/02-source-ingestion-plan.md)
4. [03-ai-analysis-plan.md](../plans/03-ai-analysis-plan.md)
5. [04-hotspot-plan.md](../plans/04-hotspot-plan.md)
6. [05-notification-plan.md](../plans/05-notification-plan.md)
7. [06-scheduler-plan.md](../plans/06-scheduler-plan.md)
8. [07-console-plan.md](../plans/07-console-plan.md)
9. [08-deploy-plan.md](../plans/08-deploy-plan.md)
10. [09-acceptance-plan.md](../plans/09-acceptance-plan.md)
11. [10-ai-hotspot-monitor-mvp-plan.md](../plans/10-ai-hotspot-monitor-mvp-plan.md)
12. [11-backend-hotspot-detection-reports-plan.md](../plans/11-backend-hotspot-detection-reports-plan.md)

## 总体目标

- 完成可自部署 AI 热点监控 MVP。
- 支持关键词管理、多源抓取、AI 查询扩展、AI 分析、热点展示、全网搜索、SMTP 事件邮件、AI 日报邮件、手动触发和简单定时触发。
- 当前执行重点为后端检测、即时搜索、日报/周报闭环；MVP 阶段暂不将控制台作为实现重点。
- 功能闭环围绕本项目 AI 热点监控 MVP 自主设计。
- PostgreSQL 作为唯一数据库。
- SQLAlchemy 作为 ORM。
- `sql/001_init_schema.sql` 作为数据库表结构事实源。
- 不使用 Alembic 或迁移文件，采用重建库策略。

## 执行约束

- 每个阶段完成后再进入下一阶段。
- 不为了兼容旧实现增加额外复杂度。
- 每个阶段必须补齐对应测试或可验收步骤。
- 新增敏感配置只允许通过环境变量注入。
