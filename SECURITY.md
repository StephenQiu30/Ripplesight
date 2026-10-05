# 安全策略

HotKey 仍在开发中，只维护 `main` 分支。

## 报告漏洞

请使用 GitHub 的 [Private Vulnerability Reporting](https://github.com/StephenQiu30/hotkey-server/security/advisories/new) 私下报告。如果该入口不可用，可以创建一个**不含漏洞细节**的 Issue，请维护者提供私密联系方式。

报告时请提供：受影响的提交、影响范围、复现条件、已脱敏的最小复现步骤。不要附上真实的密码、Token、Cookie、连接字符串或用户内容。

## 部署与数据

- 默认只绑定本机回环地址。对公网部署时，需要自行配置 HTTPS、随机凭据和备份恢复。
- `.env`、账号凭据、浏览器会话不得进入 Git、日志或公开反馈。凭据泄露时，先撤销或轮换。
- 采集边界见 [决策](workspace/content/index.md#决策)。
