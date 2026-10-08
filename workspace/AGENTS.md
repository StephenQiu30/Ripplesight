# workspace 阅读与需求核对

继承根目录 [AGENTS](../AGENTS.md)。本文件只规定文档工作区的阅读和维护方式。

项目、GitHub 主仓库与显示名称统一使用 `Ripplesight`，本机父目录为 `Ripplesight/`，仓库目录为 `ripplesight-server/` 与 `ripplesight-app/`；Compose 项目、容器、网络与自有镜像使用小写 `ripplesight` 前缀，生产项目为 `ripplesight-prod`，Pages 路径为 `/Ripplesight`。已有 `HOTKEY_*` 配置、数据库、历史数据卷、登录协议、MCP 工具名与 Obsidian 导出目录保留为兼容标识；新文案不能把它们当作品牌使用。旧路径的符号链接只用于兼容未迁移的工具与会话，新的命令和文档使用真实的新路径。

1. 从 [需求与验证入口](content/product/reference/04-需求与验证入口.md)开始，接着读 [AI 任务协议](content/product/reference/05-AI任务协议.md)及 [BACKLOG](../BACKLOG.md)的当前检查点。按当前问题选择相关需求和证据，不把整个历史计划作为一次任务。
2. 2026-10-08 最新范围：从当前页面的数据和动作收敛需求与存储，替换无页面依据的历史扩展。按页面PRD和收敛方案核对；不以文档/API/表数量作为完成标准。
3. 用户原话、已有需求、AI 提案、实现事实和运行结论明确区分。待核对文档不写成生效 PRD；未运行不写成通过。
4. 需求原文在 `content/`；任务状态唯一来源是根目录 BACKLOG。优先原位替换过时设计，不复制另一套 PRD；生效决策仍按用户要求维护。
5. 复用现有 Nextra、Markdown、索引与 AI 原文工具；本轮不扩建文档平台。单页需求必须能沿允许清单在内部知识库读取，实际独立副本/发布状态另外核对。
6. 只登记经过审查的非敏感内容；私密资料不进入公开清单，内部允许清单不等于账号授权。本轮提交推送已由用户授权，后续以最新用户指令为准。
7. 文档改动后运行 `pnpm index`、`pnpm check`、`pnpm build`。本机页面和检索另做实际检查；将检查范围与结果记录在 `VERIFICATION.md`，不把文档工具通过记成业务 POC 通过。
