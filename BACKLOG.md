# HotKey BACKLOG

更新：2026-10-06。这是唯一记录进度和优先级的地方。为什么做、版本怎么划分，见 [PRD](workspace/content/product/01-PRD.md)；每项功能怎样算完成，见对应的能力文档。

## 1. V1 每日舆情（当前版本）

完成标志：KR1、KR3、KR4 达成；KR2 达到 3 个平台。

| 顺序 | 工作 | 能力文档 | 完成条件 | 状态 |
|---|---|---|---|---|
| 1 | 启用本机 Codex 分析，并完成 200 条样本的情感评测 | [04](workspace/content/capabilities/04-评论舆情.md) | 04 验收第 2 条（KR3） | 待本人提供模型名 |
| 2 | X 每日趋势（方案 A），日报增加“今日社媒热点” | [03](workspace/content/capabilities/03-每日社媒热点.md) | 03 验收第 1、2 条（KR1） | 待派发 |
| 3 | 修复 B 站评论试点，接入微博评论 | [04](workspace/content/capabilities/04-评论舆情.md) | 04 验收第 1、4 条中的这两个平台 | 待本人在 MediaCrawler 浏览器中登录 |
| 4 | 4 个搜索来源 + 6 个热榜的真实短窗验证 | [02](workspace/content/capabilities/02-关键词热点.md) | 02 验收第 2 条 | 待派发 |
| 5 | 舆情告警（评论突增、负面占比超阈值） | [04](workspace/content/capabilities/04-评论舆情.md) | 04 验收第 3 条（KR4） | 等第 1、3 项完成 |
| 6 | 日报连续 7 天真实运行 | [05](workspace/content/capabilities/05-报告推送与知识库.md) | 05 验收第 1 条（KR1） | 等第 2 项完成 |
| 7 | 记录每天手动搜索用时的基线 | [PRD](workspace/content/product/01-PRD.md) | 第一周每天都有记录（KR5 基线） | 本人记录 |

## 2. V2 完整舆情

完成标志：KR2、KR5、KR6、KR7 达成。

| 工作 | 能力文档 | 前置 |
|---|---|---|
| 抖音、小红书评论 | [04](workspace/content/capabilities/04-评论舆情.md) | V1 第 3 项；本人登录 |
| X 账号试点（方案 B） | [03](workspace/content/capabilities/03-每日社媒热点.md) | 本人提供 token |
| 舆情看板与主题热点页 | [04](workspace/content/capabilities/04-评论舆情.md)、[02](workspace/content/capabilities/02-关键词热点.md) | V1 第 1、3 项 |
| 采集连续 72 小时稳定运行 | [02](workspace/content/capabilities/02-关键词热点.md) | V1 第 4 项 |
| 公开阅读稳定运行与抽查 | [01](workspace/content/capabilities/01-公开资讯阅读.md) | V1 第 1 项 |
| 周报真实周期、邮件真实收件 | [05](workspace/content/capabilities/05-报告推送与知识库.md) | 本人提供 SMTP |

## 3. 以后

知识库问答、模型榜真实发布、Codex 公告真实数据（依赖 X 账号试点）、Reddit（需要官方 API 获批）、补充更多热榜、登录方式的真实验收（GitHub OAuth、验证码邮件）。

## 4. 需要本人提供

| 事项 | 解锁 | 方式 |
|---|---|---|
| Codex 模型名 | V1 第 1 项 | 告诉 Claude 模型名，由开发任务写进本机配置 |
| B 站、微博、抖音、小红书登录 | V1 第 3 项、V2 | 本人在 MediaCrawler 的独立浏览器中登录 |
| X 账号 `auth_token` | V2 | 本人写进本机 `.env`，不要发给 AI |
| 通知邮件的 SMTP 凭据 | V2 | 本人写进本机 `.env` |
| GitHub OAuth App、验证码邮件 | 以后 | 同上 |
| Reddit 官方 API | 以后 | 本人申请 |

## 5. 冻结

对外分发（RSS/只读 API/MCP/Agent Markdown、SEO/IndexNow、分享海报）、Instagram/Facebook/Threads、Flutter App、通用浏览器采集、飞书推送。见 [冻结范围](workspace/content/decisions/11-冻结范围.md)。

## 6. 工作方式

由 Claude 写任务卡并派给 Codex 开发，Claude 审查和验收，分工见 [AGENTS](AGENTS.md) §1。每项工作完成后，在 `workspace/content/records/` 新建验收记录，更新对应能力文档的 `status`，并更新这里的状态。
