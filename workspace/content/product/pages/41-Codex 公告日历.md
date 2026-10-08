---
type: pointer
title: Codex 公告日历页面需求
summary: 从 /codex-resets 当前展示和操作推导字段、数量、存储与取舍
updated: 2026-10-08
---

# Codex 公告日历

路由：`/codex-resets`。角色：当前用户。范围：**现有辅助入口**。依据：当前页面和调用组件（代码基线 `67df5ab1`，本轮仅修复根元素 hydration 并移除无调用旧 header 插槽）。以下数量是现有读取策略，不是实际业务记录数，也不是容量或服务承诺。

源码入口：[page.tsx](../../../../frontend/src/app/codex-resets/page.tsx) · [codex-reset-workspace.tsx](../../../../frontend/src/app/codex-resets/components/codex-reset-workspace.tsx) · [reset-calendar.tsx](../../../../frontend/src/app/codex-resets/components/reset-calendar.tsx) · [reset-source-posts.tsx](../../../../frontend/src/app/codex-resets/components/reset-source-posts.tsx) · [reset-timeline.tsx](../../../../frontend/src/app/codex-resets/components/reset-timeline.tsx)。

## 用户任务与当前操作

作为当前用户，我需要区分官方公告、推测时间与已核实到账。当前操作围绕下表的数据完成；不从旧表和旧接口的存在反推新增产品需求。页面存在不等于来源、模型、送达或长期运行已通过真实验收。

## 页面需要的数据

| 区域／操作 | 实际展示或输入字段 | 展示数量／读取方式 | 是否持久化及最小存储 |
|---|---|---|---|
| 日历与事件 | snapshot/version/today、日期、scope/products、schedule/estimate/basis、posts/source_url | 按当前日历范围，60秒版本探测见源码；不新采集 | codex_reset_events/posts/关联 |
| 健康与原帖 | pending/review/held_window_count、filter、post翻译/原文/上下文 | 原帖按既有page参数 | monitor与scan_gaps查询 |

## 接口与业务落点

下列为本页业务读取/提交入口。全局会话、头像、站点元信息和共享组件中未在本页触发的导出函数不算新增页面能力。请求类型、响应与错误以生成客户端和后端为准。

| 页面调用 | 方法和路径 | 请求 → 响应合同 | 实现依据 |
|---|---|---|---|
| `getCodexResetConfiguration` | `GET /api/codex-resets/configuration` | `无业务入参` → `MonitorView | null` | [客户端](../../../../frontend/src/api/zhongzhigonggao.ts) · [后端](../../../../backend/app/api/routers/codex_resets.py) |
| `getCodexResetSnapshot` | `GET /api/codex-resets/snapshot` | `getCodexResetSnapshotParams` → `ResetSnapshot | null` | [客户端](../../../../frontend/src/api/zhongzhigonggao.ts) · [后端](../../../../backend/app/api/routers/codex_resets.py) |
| `getCodexResetVersion` | `GET /api/codex-resets/version` | `无业务入参` → `ResetVersionView | null` | [客户端](../../../../frontend/src/api/zhongzhigonggao.ts) · [后端](../../../../backend/app/api/routers/codex_resets.py) |
| `getRecentCodexResets` | `GET /api/codex-resets/recent` | `无业务入参` → `ResetSnapshot | null` | [客户端](../../../../frontend/src/api/zhongzhigonggao.ts) · [后端](../../../../backend/app/api/routers/codex_resets.py) |
| `listCodexResetPosts` | `GET /api/codex-resets/posts` | `listCodexResetPostsParams` → `ResetPostView[]` | [客户端](../../../../frontend/src/api/zhongzhigonggao.ts) · [后端](../../../../backend/app/api/routers/codex_resets.py) |

数据落点：[codex_reset_monitors](../reference/13-现有数据库字典.md#codex_reset_monitors)、[codex_reset_posts](../reference/13-现有数据库字典.md#codex_reset_posts)、[codex_reset_events](../reference/13-现有数据库字典.md#codex_reset_events)、[codex_reset_event_posts](../reference/13-现有数据库字典.md#codex_reset_event_posts)、[codex_reset_scan_gaps](../reference/13-现有数据库字典.md#codex_reset_scan_gaps)。这是当前依赖定位，不代表这些表均为重新设计时必须新建；详细字段/键/关系及保留原因见[页面数据库设计](../reference/09-全站页面数据库设计.md)。

## 收敛与替换

这是已有辅助专题，不把它变成通用公告订阅平台，也不据此新增X接入。

实现时先复用上述合同。确有缺口须描述具体控件、输入、输出、当前失败和最小修复，不能直接把历史扩展方案列为前置。公开分发、付费供应商、海外新来源与 Flutter 继续受[冻结范围](../../decisions/11-冻结范围.md)和其他生效决策约束。

## 验收与非功能要求

- 主路径：预计时间和官方事实区分；缺口不能显示无事件；账户权限保持。
- 数据边界：上表数量、字段和统计范围要能从响应核对；未知、未分析、无权限和真实零值不同。筛选、页签与选择不创建持久业务副本。
- 状态：有远程读取的区域分别验证正常、零数据、加载、失败和撤权；静态说明的业务空态/无权限写不适用，不伪造验收。
- 写入：有保存/运行/发布时保留可恢复输入，版本冲突先重读；请求结果未知按现有接口查询或复用原幂等键，不新增全局操作账本。
- 交互：1440px与390px下主动作可见；Tab/Enter/Escape和适用的方向键可操作，弹层关闭返回触发点。凭据只按现有认证流程传递，不进入日志/URL/本机持久存储。

测量和跨页场景统一见[非功能要求](../reference/10-全站非功能需求.md)、[验收场景](../reference/11-全站验收场景.md)。这里只定义判据，执行进度仍只在 BACKLOG。
