# 06 Scheduler Plan

## 目标

实现手动触发和简单定时触发热点检查。

## 范围

- 新建 `check_runs` 表。
- 提供手动触发 API。
- 支持轻量定时任务。
- 记录每次任务的状态、数量和错误摘要。

## 数据模型

- `id`
- `trigger_type`
- `started_at`
- `finished_at`
- `status`
- `success_count`
- `failure_count`
- `error_summary`

## API

- `POST /api/check-runs`
- `GET /api/check-runs`
- `GET /api/check-runs/{id}`

## 验收标准

- 可以手动触发热点检查。
- 简单定时任务可以复用同一条业务链路。
- 任务状态可查询。
- 来源失败、AI 失败、SMTP 失败都能记录到任务或通知状态中。

## 非目标

- P0 不强制使用 Celery/Redis。
- 不做复杂任务编排平台。
