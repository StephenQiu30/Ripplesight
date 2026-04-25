# 05 Notification Plan

## 目标

实现 SMTP 邮件通知和通知状态记录。

## 范围

- 新建 `notifications` 表。
- 使用 SMTP 发送邮件。
- SMTP 未配置时跳过邮件发送，但主流程继续。
- 记录发送成功、失败、跳过状态。

## 数据模型

- `id`
- `hotspot_id`
- `channel`
- `recipient`
- `status`
- `error_message`
- `sent_at`
- `created_at`

## 验收标准

- SMTP 配置存在时可以发送邮件。
- SMTP 配置缺失时任务继续，并记录 skipped。
- SMTP 发送失败时记录 error_message。
- 邮件内容包含标题、摘要、来源链接和相关性理由。

## 非目标

- 不做企业微信、飞书、Telegram。
- 不做复杂通知策略。
