# workspace 阅读与需求核对

继承根目录 [AGENTS](../AGENTS.md)。本文件只规定文档工作区的阅读和维护方式。

项目、GitHub 主仓库与显示名称统一使用 `Ripplesight`，本机父目录为 `Ripplesight/`，仓库目录为 `ripplesight-server/` 与 `ripplesight-app/`；新包和镜像名称使用小写 `ripplesight-` 前缀，Pages 路径为 `/Ripplesight`。已有 `HOTKEY_*` 配置、数据库、Compose 数据命名空间、登录协议、MCP 工具名与 Obsidian 导出目录保留为兼容标识；新文案不能把它们当作品牌使用。旧路径的符号链接只用于兼容未迁移的工具与会话，新的命令和文档使用真实的新路径。

1. 从 [需求与验证入口](content/product/reference/04-需求与验证入口.md)开始，接着读 [AI 任务协议](content/product/reference/05-AI任务协议.md)及 [BACKLOG](../BACKLOG.md)的当前检查点。按当前问题选择相关需求和证据，不把整个历史计划作为一次任务。
2. 2026-10-07 用户要求：当前先搭 workspace、核对需求，暂不实现业务代码；真实验证先做最小 POC 和 demo。后续明确的用户指令可更新阶段；不能由计划或源码推断已获准开工。
3. 用户原话、已有需求、AI 提案、实现事实和运行结论明确区分。待核对文档不写成生效 PRD；未运行不写成通过。
4. 需求原文在 `content/`；任务状态唯一来源是根目录 BACKLOG。不复制另一套 PRD，不删除或自动废弃已有决策。
5. 复用现有 Nextra、Markdown、索引与 AI 原文导出工具。当前不增加文档平台、编辑器、同步服务或业务实现。验证卡模板在 `content/product/reference/06-POC验证卡.md`。
6. 本轮新增内容只涉及非敏感的需求工作方式和待核对提案，登记到现有阅读清单；私密资料不进公开清单。登记可读不代表需求确认。未获授权不提交、推送或对外发布。
7. 文档改动后运行 `pnpm index`、`pnpm check`、`pnpm build`。本机页面和检索另做实际检查；将检查范围与结果记录在 `VERIFICATION.md`，不把文档工具通过记成业务 POC 通过。
