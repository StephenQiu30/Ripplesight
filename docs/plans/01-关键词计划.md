# 01 Keyword Plan

## 目标

实现关键词管理能力，作为热点监控的起点。

## 范围

- 新建 `keywords` 表。
- 支持关键词创建、更新、删除、启停。
- 支持查询模板和优先级。
- 提供 API 和控制台所需返回字段。

## 数据模型

- `id`
- `keyword`
- `query_template`
- `enabled`
- `priority`
- `created_at`
- `updated_at`

## API

- `GET /api/keywords`
- `POST /api/keywords`
- `PATCH /api/keywords/{id}`
- `DELETE /api/keywords/{id}`
- `POST /api/keywords/{id}/toggle`

## 验收标准

- 可以创建关键词。
- 可以编辑关键词和查询模板。
- 可以启停关键词。
- 已禁用关键词不会进入热点检查。
- 删除关键词后不影响历史热点展示。

## 非目标

- 不做多用户关键词隔离。
- 不做复杂规则引擎。
