---
layer: Plan
scope: issue
doc_no: "010"
title: MediaCrawler 三类版本证据执行计划
status: in_progress
version: v1.1
date: 2026-09-26
owner: HotKey Team
canonical_path: docs/plan/010-MediaCrawler三类版本证据执行计划.md
prd: docs/prd/003-本人账号B站试点需求.md
design: docs/design/003-本人账号B站试点设计.md
architecture_prerequisite: "046 S03"
source_task: TASK-003-S01-T01
depends_on: ["002"]
---

# Plan 010：MediaCrawler 三类版本证据

2026-09-28 技术进度：运行前版本门禁核对固定根 realpath、Git 根/HEAD、已跟踪差异与未跟踪可执行/代码文件；失败归为 `configuration_unavailable`。三类版本已分别写入组件策略和受理时 Job 快照，旧 Job 换版不变，失败 Job 保留版本与错误码，缺失/不符快照在适配器装配前拒绝。临时 Git 工作树和隔离 PostgreSQL 17 均已受控验证；本机固定目录只读检查因 HEAD 不符拒绝，真实账号未请求。实际固定目录修复与 Plan012 真实 Job 关联仍待本人核对，故本卡保持 `in_progress`。

G0 核对：历史 `68f1b02b` 的 046 S03 验收全项 `passed`；Plan002 已完成预设/预算同事务与连接版本快照。实施前 B 站 `component_version` 仍指向上游短版，Job 无三类版本列。当前切片修改 `sources/adapters/mediacrawler.py`、`connections/{presets,services}.py`、`jobs/{schemas,models,services}.py`、`content/{discovery_execution,comments_execution}.py`、`backend/database/schema.sql`、相关单元/集成测试及本设计、Plan、Acceptance、BACKLOG；新增 `backend/tests/integration/test_mediacrawler_evidence.py`。未修改 HTTP 路由或生成客户端。

## 固定字段与实施路径

修改 `backend/app/sources/adapters/mediacrawler.py`、`connections/presets.py`、`jobs/schemas.py`、`jobs/models.py` 与唯一schema。上游 `380b426000aac3d612837ed72c99808347dc94c9`、Plan011 后固定补丁提交 `1bd07bc783963acef092ff00771207b7792b8cb6`、适配器 `mediacrawler-1bd07bc-hotkey-safe` 分别写入固定Job配置/执行证据字段；组件策略存基线与补丁引用，实际运行证据关联operation_id、job_id、connection_version。旧历史只有component_version时标版本证据不完整，不反填虚假三版本。

校验固定目录realpath、HEAD和tracked diff，先于子进程/任何平台请求；错误稳定分类为 `mediacrawler_revision_mismatch`、`mediacrawler_worktree_dirty`、`mediacrawler_version_evidence_missing`，失败不映射认证失效。只允许已配置固定根，未受控可执行文件/未跟踪代码可能影响执行时同样拒绝，runtime私有输出按明确白名单隔离，不修改外部工作树或自动打补丁。

- [x] CHK-010-101 → SEC/JOB：`backend/tests/unit/test_mediacrawler_adapter.py` 使用临时受控Git夹具验证错HEAD、dirty、越界路径及额外可执行文件，断言子进程启动计数0。
- [x] CHK-010-102 → DATA：`backend/tests/integration/test_mediacrawler_evidence.py` 断言三字段分别持久、换版旧Job不变、失败Job也可定位版本检查结果。

运行B门禁；真实固定工作树只读检查，实际账号请求归012。结果归M2 Acceptance Plan010；不因外部工作树存在就宣称来源接入。

## 范围与需求

旧B站预设component_version与固定补丁不一致。本卡按 [PRD 003](../prd/003-本人账号B站试点需求.md) FR-003-002、NFR-003-001和AC-003-001/002/003分别保存三类版本与Job关联；依赖002版本策略，具体字段/文件与校验顺序已在本文定义，与011共用文件的修改按依赖顺序进行。

## SPEC

| ID | 规格 |
|---|---|
| `SPEC-010-SEC-001` | 运行前核对上游基线、补丁后 HEAD 和已跟踪文件未改动；固定工作树不符则拒绝启动，不读取任意路径或回显资料。 |
| `SPEC-010-DATA-001` | Job 分别记录上游基线、补丁提交、实际适配器版本及来源连接版本，不能以单个 `component_version` 混记三类事实。 |
| `SPEC-010-JOB-001` | 版本校验先于子进程启动；校验失败记明确停止状态，不消耗真实采集结果名额。 |

## 验收与 Checklist

Given：固定补丁工作树和三类版本标识可读。When：分别以正确、脏工作树、错 HEAD 启动受控 Job。Then：仅符合固定版本的 Job 可以继续，版本证据在 Job 可独立追溯。

- [x] `CHK-010-G0-001`：核对 PRD/Design、046 S03、Plan 002 与当前预设差异，列确切文件。
- [x] `CHK-010-G1-001`：冻结三类版本字段、校验顺序和错误码。
- [x] `CHK-010-G2-001`：先保存正确/错误 HEAD、已跟踪文件改动和版本缺失的失败验证。
- [x] `CHK-010-G3-001`：实现并核对 `SPEC-010-SEC-001`、`SPEC-010-DATA-001`、`SPEC-010-JOB-001` 与 Job 关联。
- [x] `CHK-010-G4-001`：运行 Ruff/mypy/pytest、真实库 Job 持久化和进程启动边界测试。
- [ ] `CHK-010-G5-001`：本人账号真实低频采集前只读核对三类实际版本，并在 Plan 012 的真实 Job 验证关联。
- [x] `CHK-010-G6-001`：记录 `AC-003-001/002/003` 的版本部分；采集和风控结果另验。

失败时保持 B 站来源关闭，保留原 Job 和错误证据；不得自动切换工作树或补丁。受控、真实与产品证据分别登记。
