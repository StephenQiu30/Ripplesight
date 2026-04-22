# Infrastructure Layer

职责：

- X API 适配器
- NewsAPI / GDELT / RSS 适配器
- 数据库访问
- Redis / Celery 接入
- Resend 邮件发送

约束：

- 对外部 API 的超时、重试、限流和降级策略应在此层统一治理
