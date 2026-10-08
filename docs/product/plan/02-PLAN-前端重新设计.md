---
type: plan
title: PLAN：前端重新设计
summary: 按Figma从layout重建主页面，替换历史八张任务卡
status: 生效
updated: 2026-10-08
---

# PLAN：前端重新设计

本版替换旧八张任务卡。“不能改外壳”“缺数据隐藏模块”“默认四页签”“取消备注”等限制已被用户最新要求覆盖；历史由Git追溯，不再混入当前计划。

## 实施顺序

1. 从Figma桌面原稿统一layout、侧栏、正文、字体/令牌和shadcn组件。
2. 重建首页、探索、事件、日报、榜单、监控、收藏和登录，移除旧展示组合；保留权限、会话、草稿、任务幂等与许可。
3. 以[页面PRD](../prd/03-PRD-全站页面需求.md)持久化字段/数量/操作/服务缺口，不另复制任务卡。
4. 1440px/390px验证五状态和键盘，跑工程检查；受控样本和真实业务分开记录。
5. 按[接口](../reference/08-全站页面接口设计.md)及[数据库](../reference/09-全站页面数据库设计.md)分切片承接缺口，优先查询复用。

## 约束

视觉以[Figma](https://www.figma.com/design/DfWRfnw965ocH6lmlSYGgs)与[DESIGN](../../../frontend/DESIGN.md)为准。使用shadcn/Radix，遵循Vercel React的并行读取和客户端边界建议。设计示例不入产品；缺数据保留空态，后台辅助路由收进更多。

用户授权提交推送main。真实采集、发信和业务库迁移不因视觉验收自动执行。工程及Claude审查遵守[AGENTS](../../../AGENTS.md)，进度只记[BACKLOG](../../../BACKLOG.md)。
