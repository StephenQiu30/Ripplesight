---
layer: PRD
doc_no: "09"
audience:
  - PM
  - Dev
  - QA
  - Ops
feature_area: backend-operability
purpose: "定义企业级 P0 环境级真实链路验收的范围、证据要求与失败边界。"
canonical_path: "docs/product/prd/09-生产环境回放验收PRD.md"
status: draft
version: "0.1.0"
owner: "StephenQiu30"
inputs:
  - "docs/engineering/验收标准.md（需真实配置后验收）"
  - "docs/enterprise-p0-backlog-gap-review.md"
  - "docs/plans/17-生产环境回放与凭据验收计划.md"
outputs:
  - "企业级 P0 生产链路可复验的证据清单"
  - "真实凭据场景的验收流程与失败处理结论"
triggers:
  - "企业级 P0 启动并进入阶段 B1"
  - "需要确认 PostgreSQL、X/Twitter、Bing、SMTP、模型在真实环境可执行时"
downstream:
  - "docs/plans/17-生产环境回放与凭据验收计划.md"
  - "docs/验收差距清单.md"
---

# 生产环境回放验收 PRD（B1）

## 1. 背景

企业级 P0 补齐不再停留在本地降级路径，必须补足真实配置下的可复现链路，确保：
- PostgreSQL 可正常初始化与写入；
- 关键外部源与模型在有凭据时可回放；
- 任务执行后的热点、报告、通知状态可完整回查。

## 2. 目标（SMART）

- **S**pecific：在一轮回放中完成关键词配置、抓取、AI 扩展与分析、热点入库、报告、邮件路径的闭环。
- **M**easurable：每类凭据场景均留下至少一条命令日志、时间戳、对应的请求 ID 或记录编号。
- **A**chievable：仅依赖现有 `docker-compose.prod.yml` + 环境变量，不新增新平台。
- **R**elevant：用于把企业级 P0 的真实运行缺口从“待补齐”转为“可验收”。
- **T**ime-bound：单次回放在 4 小时内完成并能复现。

## 3. 非目标

- 不引入新外部服务；
- 不改造现有热点主流程代码；
- 不要求性能压测或高并发灾备测试；
- 不要求对旧实现兼容。

## 4. 功能定义与验收项

- 真实环境初始化
  - 使用 PostgreSQL 空实例执行 `sql/001_init_schema.sql` 完成初始化。
  - 记录建库与初始化命令，确认 `keywords/sources/hotspots/check_runs/reports` 可读写。

- 真实来源回放
  - 配置并验证 X/Twitter、Bing 至少一次真实返回。
  - 关键字段包括但不限于候选数量、来源类型、入库成功/跳过原因。

- 模型与报告链路
  - 配置并验证 OpenAI 兼容模型（或兼容网关）参与查询扩展与热点分析。
  - 触发一次检查并生成 daily/weekly 报告。

- 通知链路
  - 真实 `SMTP_*` 配置下完成事件邮件或报告邮件至少一次发送。

- 存证与回放复核
  - 保存一份 `B1-回放证据清单.md`（命令、时间、输出、失败项、恢复动作）。

## 5. 运行标准场景（Given-When-Then）

- 场景 1：真实数据库可用
  - Given PostgreSQL 空库。
  - When 初始化并启动关键词抓取任务。
  - Then 任务成功落库并能查询检查结果。

- 场景 2：真实源可用
  - Given 配置 X 与 Bing 凭据。
  - When 触发一次检查。
  - Then 至少一条来源返回候选且系统不中断。

- 场景 3：邮件真实发送
  - Given SMTP 配置完整。
  - When 触发事件或日报/周报。
  - Then 至少一条邮件发送成功记录可见。

## 6. 风险与边界

- 外部接口速率限制、密钥配额不足导致回放不完整；
- 邮件通道被 SPF/DKIM 拒绝导致发送失败；
- 模型服务冷启动导致长耗时，需要记录重试策略。

## 7. 交付与验收

- `docs/plans/17-生产环境回放与凭据验收计划.md` 完成。
- `docs/验收差距清单.md` 与 `docs/enterprise-p0-backlog-gap-review.md` 更新为“B1 已闭环”。
- 所有原始命令输出与异常日志可复现。

## 8. 变更记录

| 日期 | 作者 | 版本 | 变更说明 |
| --- | --- | --- | --- |
| 2026-05-24 | StephenQiu30 | 0.1.0 | 新建 B1 企业级 P0 生产链路回放 PRD |
