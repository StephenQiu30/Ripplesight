# Worker Service

该目录只承担 `Celery` worker、beat 和任务入口装配职责。

约束：

- 不复制 API 服务中的业务逻辑
- 定时采集、日报生成、邮件推送等任务只调用 `backend/core/` 中的应用层能力
- 任务日志与错误模型需要与 API 服务保持一致
