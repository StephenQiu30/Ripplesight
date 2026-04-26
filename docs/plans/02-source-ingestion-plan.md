# 02 Source Ingestion Plan

## 目标

实现多来源抓取和统一标准化输入，并支持本项目 P0 选定的多平台信息源。

## 范围

- 新建 `sources` 表。
- 支持 RSS、Hacker News、X/Twitter、Bing、Bilibili、Sogou-style 返回热点候选。
- 支持来源启停。
- 单个来源失败不影响整体任务。

## 数据模型

- `id`
- `name`
- `source_type`
- `enabled`
- `config`
- `created_at`
- `updated_at`

## 来源策略

- P0 优先实现公开、低门槛来源。
- X/Twitter 为可选来源，未配置凭据时跳过。
- Bing 为可选来源，未配置凭据时跳过。
- Bilibili 和 Sogou-style 为 best-effort 来源，失败时只记录错误。
- 每个来源输出统一候选字段：标题、URL、作者、发布时间、摘要片段、原始 payload。

## 验收标准

- 至少两个来源可被调用。
- X/Twitter 未配置 `X_API_BEARER_TOKEN` 时跳过且不中断任务。
- Bing 未配置 `BING_SEARCH_API_KEY` 时跳过且不中断任务。
- 来源失败会记录错误，但任务继续。
- 禁用来源不会被调用。
- 候选内容能进入统一标准化流程。

## 非目标

- 不做全网 firehose。
- 不做视频平台复杂采集。
- 不保存完整第三方正文。
