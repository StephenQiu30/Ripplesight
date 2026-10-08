---
type: record
title: docs 与 Obsidian 文档管理迁移
summary: 撤销在线项目文档设施，恢复 docs 原文与 Obsidian 文件管理；实际 Obsidian 操作仍待验收
capability: capabilities/07-项目文档知识库.md
criterion: 文档管理验收标准1与2
result: 通过
date: 2026-10-08
updated: 2026-10-08
---

# docs 与 Obsidian 文档管理迁移

## 来源与范围

用户决定不使用在线知识库，恢复 docs 下的文档管理并保留 Obsidian。原文、模板、Bases、共享配置、设计参考与旧验证记录迁入 docs；根文件保持唯一原文。原网页专项 PRD/PLAN 标为废弃，根文件章节链接直接定位真实来源。

移除 Nextra 站、项目文档网页/API、专用快照/发布工具、Compose 文档服务与 Pages 工作流，改为 scripts/docs 的文件索引/校验 CI。共用业务阅读器、Editor.js 块格式类型及业务 Obsidian 导出保留。现有前端侧栏并行改动原样保留。

## 证据

- 归档 content 全部127个文件均有 docs 对应文件；模板、Bases、全部 Obsidian 配置与设计参考逐字节保留；仅3个共享 Obsidian 配置可提交，个人状态被忽略。
- 文档 index/check、独立只读审查、全部 Markdown 本地链接扫描通过。新工具不构建或发布文档网站。
- 后端 Ruff、格式与 mypy通过；完整普通pytest为1623通过、958跳过，无失败；新增API退役断言与Obsidian导出专项35通过。跳过包含需独立数据库及外部条件的集成测试，本轮未跑完整业务库集成。
- Web lint、typecheck、format:check、122文件1019项测试和生产build通过；生成客户端按当前源码启动的18667 API更新，openapi:check无差异。
- 开发/生产全部profile Compose配置通过；本机旧workspace容器停止并删除，8668无监听；8667 OpenAPI已无项目文档路由，8666健康接口200。临时契约API已关闭。

## 保留与局限

旧站与生成物保留在Git忽略的 `.tools/retired-workspace-2026-10-08/`，未自动迁入私密副本或删除业务数据。未提交推送，远端GitHub Pages历史发布仍存在；本轮只移除当前工作区发布流程并停本机文档服务。

文件检查不替代真实Obsidian打开vault、检索、模板与Bases操作验收，也不代表业务能力或全站浏览器验收通过。该真实操作继续待验收。
