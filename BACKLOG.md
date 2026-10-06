# HotKey BACKLOG

更新：2026-10-06。这是唯一记录进度和优先级的地方。为什么做、版本怎么划分，见 [PRD](workspace/content/product/prd/01-PRD.md)；每项功能怎样算完成，见对应的能力文档。

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
| 7 | 记录每天手动搜索用时的基线 | [PRD](workspace/content/product/prd/01-PRD.md) | 第一周每天都有记录（KR5 基线） | 本人记录 |

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

## 7. 项目文档知识库（独立排期）

需求见[workspace 项目知识库专项 PRD](workspace/content/product/prd/02-PRD-workspace项目知识库.md)，任务验收、负责人、估算与依赖见[执行计划](workspace/content/product/plan/01-PLAN-workspace项目知识库.md)。专项按全天每两小时推进一轮规划，周期任务尚未配置；业务 V1/V2 的优先级保持现有顺序。

首个 Sprint 的启动包为工具修复与方案收敛，共 16 理想小时，均尚未派发；其余是待前置完成后滚动准入的候选。按计划初值，首个 Sprint 全部候选合计 128 小时，后续编辑 Sprint 116 小时。真实容量在前 12 个窗口后校准。

### 首个 Sprint：阅读与 AI

| 顺序 | 工作与任务卡 | 完成条件 | 状态 |
|---|---|---|---|
| 1 | [文档工具修复](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#文档工具修复) | 当前文档校验与构建可重复通过，支持 plan 元数据 | 待派发；启动包 |
| 2 | [方案收敛](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#方案收敛) | 技术方案、能力归属、环境与身份缺口明确 | 待派发；启动包 |
| 3 | [来源清单与版本快照](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#来源清单与版本快照) | 唯一原文、文件 hash、可重建的同版本快照 | 待前两项完成；候选 |
| 4 | [统一权限与读取接口](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#统一权限与读取接口) | 全读取出口授权与路径校验，生成契约通过 | 待来源快照与本人身份确认；候选 |
| 5 | [工作台阅读界面](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#工作台阅读界面) | 同布局文档显示、链接与五种页面状态正确 | 待读取契约；候选 |
| 6 | [Obsidian 离线阅读](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#obsidian-离线阅读) | 实际 vault 离线阅读，根文件定位正确 | 待来源快照及 vault 验收；候选 |
| 7 | [目标环境读取验证](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#目标环境读取验证) | KR1、KR2 真实验收与冷启动、恢复记录 | 待接口、页面及目标环境；候选 |
| 8 | [中文检索](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#中文检索) | KR3 固定 20 条至少 18 条在前 5 命中 | 待阅读门槛通过；候选 |
| 9 | [AI 原文读取与引用](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#ai-原文读取与引用) | 授权逐页或章节读取，同版本引用可打开 | 待检索与本机 Codex 可用；候选 |
| 10 | [阅读与 AI 验收](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#阅读与-ai-验收) | KR1—KR4；真实 Codex、查询和边界问题记录 | 待前述产物及验收时间；候选 |

### 后续 Sprint：双端编辑

| 顺序 | 工作与任务卡 | 完成条件 | 状态 |
|---|---|---|---|
| 1 | [编辑与同步设计](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#编辑与同步设计) | 草稿、Git 副本、写入位置、确认与恢复明确 | 待阅读与 AI 门槛；候选 |
| 2 | [草稿接口](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#草稿接口) | 原文保存、CSRF、版本校验与重启恢复 | 待设计及可写存储；候选 |
| 3 | [Markdown 编辑界面](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#markdown-编辑界面) | 原文编辑、差异、草稿与发布状态清楚 | 待草稿契约；候选 |
| 4 | [确认发布](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#确认发布) | 限定路径发布，同版本切换与未知结果核对 | 待草稿、界面、Git 副本与发布授权；候选 |
| 5 | [版本冲突处理](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#版本冲突处理) | 双方差异保留，无静默覆盖 | 待草稿与发布操作；候选 |
| 6 | [Obsidian 双端同步](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#obsidian-双端同步) | 五类样本十条往返，原文与元数据不丢失 | 待冲突处理及真实 vault；候选 |
| 7 | [历史恢复](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#历史恢复) | 确认后恢复已知版本，历史与草稿保留 | 待发布历史；候选 |
| 8 | [编辑验收](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#编辑验收) | KR5、KR6 真实双端往返与全部异常恢复 | 待写入任务、真实环境及验收时间；候选 |

远程只读 MCP 按具体客户端需求单独估算与派发，不作为首期前提；不恢复业务公开分发范围。更新任务状态时同时记录证据与阻塞条件，不将候选任务、受控测试或周期运行次数当作已完成。
