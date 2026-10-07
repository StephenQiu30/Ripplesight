# Ripplesight BACKLOG

更新：2026-10-07。这是唯一记录进度和优先级的地方。为什么做、版本怎么划分，见 [PRD](workspace/content/product/prd/01-PRD.md)；每项功能怎样算完成，见对应的能力文档。

## 当前检查点：先核对需求，再做最小验证

2026-10-07 本人指出文档与真实执行存在理解和实现偏差，范围总做得又大又全，要求先搭 workspace，暂不实现业务代码；真实验证应先跑通 POC 和 demo。原话与阅读入口见[需求与验证入口](workspace/content/product/reference/04-需求与验证入口.md)。

本轮只整理文档入口、AI 阅读约定、验证卡和本机阅读验证。首个业务 POC 场景尚未选定，[热点事件需求核对](workspace/content/research/2026-10-07-热点事件需求核对.md)仅是候选；没有业务编码或业务验证结果。完成情况见 [workspace 验证记录](workspace/VERIFICATION.md)。

本轮状态：需求入口、AI 协议、验证卡和本机预览已搭好；文档校验、构建、34 页 HTTP/原文导出及浏览器 POC 搜索通过。当前 Codex 已按导出原文核对阶段、候选状态和证据边界；本人对阅读体验与首个业务场景的反馈待收到，正式账号知识库和双端编辑未验收。

随后按本人要求统一名称为 Ripplesight：GitHub 仓库已改名，本机 origin 已更新；页面、文档、包、镜像默认名称与 Pages 路径已调整并在本机验证。源码改名尚未提交、推送或部署；线上 Pages 仍引用旧路径，资源返回 404，需发布新构建。改名不迁移既有数据库、登录或导出数据，也不代表业务 POC 已通过；详细证据见上述 workspace 验证记录。

同日补齐文件夹与描述：父工作区迁为 `Ripplesight/`，主仓库与冻结客户端分别为 `ripplesight-server/`、`ripplesight-app/`；App 远端改为 `Ripplesight-app`。GitHub About、README、页面与包描述同步当前用途，App 明确仍冻结。旧路径以兼容链接保留；Codex 保存的项目名称/路径未自动更新，界面修改被安全限制拒绝，需手动切换到新目录。新路径下工程、文档与 App 说明检查通过；没有提交、推送或部署。

下列 V1/V2、知识库和前端计划及历史状态原样保留，供逐项核对；当前阶段不据这些列表继续派发业务实现。§7 中记载的 heartbeat 是历史运行方式，本轮没有修改其配置；读到这里的后续任务也应遵守本轮范围与最新用户指令。

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

需求见[workspace 项目知识库专项 PRD](workspace/content/product/prd/02-PRD-workspace项目知识库.md)，任务验收、负责人、估算与依赖见[执行计划](workspace/content/product/plan/01-PLAN-workspace项目知识库.md)。当前聊天已启用全天每两小时推进一次的 heartbeat（`hotkey`）；业务 V1/V2 的优先级保持现有顺序。

首个 Sprint 的启动包为工具修复与方案收敛，共 16 理想小时，已开始工具修复与方案收敛；其余是待前置完成后滚动准入的候选。按计划初值，首个 Sprint 全部候选合计 128 小时，后续编辑 Sprint 116 小时。真实容量在前 12 个窗口后校准。

本次范围为开发过程的内部知识库：现有 frontend 内接入 Nextra，网页编辑采用 Editor.js 与 Markdown 原文视图，管理 PRD、决策、计划及关联；不采用 GitBook。内部调研记录 `workspace/content/research/2026-10-06-workspace成熟方案调研.md` 包含作者 workspace 范式与 Notion 替代路线，Notion 尚未采用。目标环境已确认只在本机运行，框架与格式适配复用现有实现；不安装 Fumadocs，不删除现有 Nextra。

### 首个 Sprint：阅读与 AI

| 顺序 | 工作与任务卡 | 完成条件 | 状态 |
|---|---|---|---|
| 1 | [文档工具修复](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#文档工具修复) | 当前文档校验与构建可重复通过，支持 plan 元数据 | 工程检查与本地浏览器复核通过，待 Claude 审查；证据见 [VERIFICATION](workspace/VERIFICATION.md#本轮工具修复与编号复核) |
| 2 | [方案收敛](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#方案收敛) | 技术方案、能力归属、环境与身份缺口明确 | 源码核对与方案草案已整理至 [PROJECT §11](PROJECT.md#11-项目文档知识库接入方案待审查)，已建立 [07 能力](workspace/content/capabilities/07-项目文档知识库.md)；仅本机环境已确认；待 Claude 审查及本人账号配置 |
| 3 | [来源清单与版本快照](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#来源清单与版本快照) | 唯一原文、文件 hash、可重建的同版本快照 | 本机工具已实现，确定性与完整性测试通过；待审查与真实初始化 |
| 4 | [统一权限与读取接口](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#统一权限与读取接口) | 全读取出口授权与路径校验，生成契约通过 | 接口与生成客户端已实现，受控权限检查通过；待本人 UUID 与真实身份验收 |
| 5 | [工作台阅读界面](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#工作台阅读界面) | 同布局文档显示、链接与五种页面状态正确；Nextra 保留且内部快照隔离 | Nextra 入口已实现；桌面、390px 五种状态与键盘受控验证通过；待审查与真实验收 |
| 6 | [Obsidian 离线阅读](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#obsidian-离线阅读) | 实际 vault 离线阅读，根文件定位正确 | 专用副本、根文件映射与使用说明已准备；实际 Obsidian 尚未验收 |
| 7 | [目标环境读取验证](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#目标环境读取验证) | KR1、KR2 真实验收与冷启动、恢复记录 | 本机隔离样本已验证；真实账号配置、冷启动及正式 KR 验收待完成 |
| 8 | [中文检索](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#中文检索) | KR3 固定 20 条至少 18 条在前 5 命中 | 同快照关键词检索与浏览器冒烟已实现；固定 20 条查询尚未验收 |
| 9 | [AI 原文读取与引用](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#ai-原文读取与引用) | 授权逐页或章节读取，同版本引用可打开 | 授权 API、本机只读 CLI 与章节定位已实现；真实本机 Codex 问题集尚未验收 |
| 10 | [阅读与 AI 验收](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#阅读与-ai-验收) | KR1—KR4；真实 Codex、查询和边界问题记录 | 待前述产物及验收时间；候选 |

### 后续 Sprint：双端编辑

| 顺序 | 工作与任务卡 | 完成条件 | 状态 |
|---|---|---|---|
| 1 | [编辑与同步设计](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#编辑与同步设计) | 草稿、Git 副本、写入位置、确认与恢复明确 | 本机方案与实现见 PROJECT §11、LOCAL；待 Claude 审查 |
| 2 | [草稿接口](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#草稿接口) | 原文保存、CSRF、版本校验与重启恢复 | 已实现，受控版本、CSRF 与持久恢复检查通过；待真实账号验收 |
| 3 | [Markdown 编辑界面](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#markdown-编辑界面) | 富文本与原文共用草稿，差异与发布状态清楚，格式保留 | Editor.js、原文、预览与对比已实现，真实编辑器保存及格式测试通过；待实际双端与输入法验收 |
| 4 | [确认发布](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#确认发布) | 限定路径发布，同版本切换与未知结果核对 | 独立 Git 发布、决策替代与结果核对已实现；隔离副本浏览器发布通过，待审查与真实授权验收 |
| 5 | [版本冲突处理](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#版本冲突处理) | 双方差异保留，无静默覆盖 | 隔离样本验证保存冲突、保留双方、显式合并后发布；待真实验收 |
| 6 | [Obsidian 双端同步](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#obsidian-双端同步) | 五类样本十条往返，原文与元数据不丢失 | 文件同步工具已实现；实际 Obsidian 的五类十条往返尚未验收 |
| 7 | [历史恢复](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#历史恢复) | 确认后恢复已知版本，历史与草稿保留 | 版本历史、加载新草稿与历史只读入口已实现；待完整恢复场景验收 |
| 8 | [编辑验收](workspace/content/product/plan/01-PLAN-workspace项目知识库.md#编辑验收) | KR5、KR6 真实双端往返与全部异常恢复 | 待写入任务、真实环境及验收时间；候选 |

远程只读 MCP 按具体客户端需求单独估算与派发，不作为首期前提；不恢复业务公开分发范围。更新任务状态时同时记录证据与阻塞条件，不将候选任务、受控测试或周期运行次数当作已完成。


### 外部条件与下一检查点

| 条件 | 负责人 | 当前影响与检查点 |
|---|---|---|
| 工具与接入方案审查 | Claude | 已尝试本机只读审查，Claude 登录过期，审查未执行；重新登录后复核当前修改，不能将工程通过记为代码完成 |
| 正式验收环境及允许的本人账号 | Stephen | 本机环境已确认；已请求现有账号 UUID，核对后只写本机配置，不记入公开文档。无配置时读取关闭 |
| 私密作者目录与文档专用 Git 工作副本 | Stephen 确认；Codex 配置 | 现有公开资料可准备本地样本；初始化在 .tools/workspace/source 建立独立来源，移除远端；待本人配置账号与实际使用验收 |
| 目标快照挂载与持久草稿存储 | Stephen 确认；Codex 实现 | §11 提供本机持久快照和草稿方案；冷启动、恢复和真实写入需在确认的目标环境验证 |
| 实际 Obsidian vault | Stephen；Claude 验收 | 工程文件校验不代表离线操作与双端往返已验收 |

当前检查点：`286e4dbe` 的分类与编号、`8d562ced` 的文档工具已推送 main。本轮新增本机授权接口、Nextra 阅读入口、Editor.js 与原文草稿、隔离 Git 发布、决策替代及操作核对。启动说明见 [本机知识库](workspace/LOCAL.md)，工程证据见 [本机接入验证](workspace/VERIFICATION.md#本机知识库接入验证)。工程与受控浏览器检查通过；真实账号、Obsidian、本机 Codex 和 Claude 审查未完成，不将实现记为能力可用。

## 8. 前端重新设计（独立排期）

依据 2026-10 高保真稿（[Claude 画布](https://claude.ai/artifact/ERFs389e9sFhhp11U5cviY)、[Figma](https://www.figma.com/design/DfWRfnw965ocH6lmlSYGgs)）与 [DESIGN](frontend/DESIGN.md) 重做 Web 外壳和主要页面，只用现有接口与真实数据。任务卡、数据缺口与验收见[执行计划](workspace/content/product/plan/02-PLAN-前端重新设计.md)。一次只派一张卡，与其他 frontend 写入任务串行。

| 顺序 | 工作与任务卡 | 完成条件 | 状态 |
|---|---|---|---|
| 1 | [外壳与公共状态](workspace/content/product/plan/02-PLAN-前端重新设计.md#1-外壳与公共状态) | 新侧栏、底部导航、PageState；全部一级路由在新外壳下正常 | 2026-10-07 完成，见[验收记录](workspace/content/records/2026-10-06-前端重新设计验收.md) |
| 2 | [首页](workspace/content/product/plan/02-PLAN-前端重新设计.md#2-首页) | 真实数据下各块正确，单块失败不影响整页 | 2026-10-07 完成，见[验收记录](workspace/content/records/2026-10-06-前端重新设计验收.md) |
| 3 | [事件详情](workspace/content/product/plan/02-PLAN-前端重新设计.md#3-事件详情) | 公开与工作台入口、有无代表评论两类事件均正确 | 2026-10-07 完成，见[验收记录](workspace/content/records/2026-10-06-前端重新设计验收.md)；真实事件数据待有后复核 |
| 4 | [探索与收藏](workspace/content/product/plan/02-PLAN-前端重新设计.md#4-探索与收藏) | 筛选可分享，本机收藏刷新后保持 | 2026-10-07 完成，见[验收记录](workspace/content/records/2026-10-06-前端重新设计验收.md) |
| 5 | [日周月刊阅读](workspace/content/product/plan/02-PLAN-前端重新设计.md#5-日周月刊阅读) | 最新与归档各一期、打印预览正确 | 2026-10-07 完成，见[验收记录](workspace/content/records/2026-10-06-前端重新设计验收.md) |
| 6 | [工作台：监控主题与告警](workspace/content/product/plan/02-PLAN-前端重新设计.md#6-工作台监控主题与告警) | 真实会话下主题与告警增改停复各一次 | 2026-10-07 完成，见[验收记录](workspace/content/records/2026-10-06-前端重新设计验收.md)；告警创建待通知目标配置 |
| 7 | [模型榜](workspace/content/product/plan/02-PLAN-前端重新设计.md#7-模型榜) | 各维度与子页可用，空数据有空状态 | 2026-10-07 完成，见[验收记录](workspace/content/records/2026-10-06-前端重新设计验收.md) |
| 8 | [登录页](workspace/content/product/plan/02-PLAN-前端重新设计.md#8-登录页) | 三种方式在已配置与未配置下显示正确 | 2026-10-07 完成，见[验收记录](workspace/content/records/2026-10-06-前端重新设计验收.md) |
