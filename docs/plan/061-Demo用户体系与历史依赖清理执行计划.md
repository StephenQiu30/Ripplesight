---
layer: Plan
scope: issue
doc_no: "061"
title: Demo用户体系与历史依赖清理执行计划
status: completed
version: v1.0
date: 2026-10-01
owner: HotKey Team
canonical_path: docs/plan/061-Demo用户体系与历史依赖清理执行计划.md
prd: docs/prd/001-热点舆情监控平台需求.md
design: docs/design/001-热点舆情监控平台总体设计.md
source_task: 用户要求直接清理历史代码与页面且Demo无需登录注册及用户体系
architecture_prerequisite: "046 S03"
depends_on: []
---

# Plan061：Demo 用户体系与历史依赖清理

## 1. 范围与前置

承接用户2026-10-01最新决定和 Design001 §9.2。删除身份实现及其业务页面依赖，直接使用当前 Demo。未来 ToC 账户要求延后，不实施060、不增加 fake user/session、AUTH_DISABLED 或通用认证框架。保留来源授权、B站凭据、内容身份、任务幂等和预算。历史046 S03 passed 证据见 `68f1b02b:docs/acceptance/046-全局异常与响应契约验收.md` 与 Acceptance002 G0；本片重新验证HTTP和生成客户端。

## 2. 文件与职责

| 分类 | 路径 | 责任 |
|---|---|---|
| 新增 | `backend/app/db/demo.py` | 全业务元数据解析唯一历史分区，不建立身份 |
| 删除 | `backend/app/identity/`、`api/routers/identity.py` | 身份、密码、会话、初始化及工作区接口 |
| 修改 | `api/{router,dependencies,exception_handlers}.py`、业务 routers | UUID分区注入、写入头、错误与响应契约 |
| 修改 | `db/metadata.py`、8领域`models.py`、`database/schema.sql` | 删除身份注册与外键，保留业务UUID/复合约束 |
| 修改 | `core/{config,errors}.py`、`cli/{commands,jobs}.py`、`backups/restore.py`、`jobs/coverage.py` | 删除身份配置/CLI，业务回滚探针，覆盖查询显式管理读取事务 |
| 修改 | `pyproject.toml`、`uv.lock`、配置模板、Compose、CI、测试夹具 | 删除部署密钥、密码库及旧身份验证前置 |
| 删除 | `frontend/src/app/{login,register}/`、`components/auth/` | 登录注册及独占凭据组件 |
| 修改 | `proxy.ts`、`request.ts`、同源API代理、首页/业务页面组件 | 去守卫、会话请求、账户/退出与401跳转，保留CSP/错误恢复 |
| 生成 | `frontend/src/api/` | 从实际 `/openapi.json` 重新生成，不手改 |
| 修改 | 相关后端/前端 tests、README、PROJECT、AGENTS、PRD/Design、台账 | 行为和现状一致，旧证据仍标历史 |

页面专属组件沿用原路径；`EventsWorkspace` 数据源为 topics，`TopicForm` 为 source capabilities。两者及列表/详情组件覆盖加载、空、业务错误/重试、成功与窄屏，不新增公共feature层。

## 3. SPEC

- SPEC-061-001：读取业务API无需Cookie；身份API和登录注册页面删除（404），OpenAPI无身份路径或会话security scheme。写请求使用固定`X-HotKey-CSRF: 1`，错误值/缺失403 `csrf_invalid`；代理不传旧身份Cookie/Authorization，不返回旧Set-Cookie。
- SPEC-061-002：从全部已注册业务表取不同owner_id，空库固定UUID `00000000-0000-4000-8000-000000000001`，唯一值复用，多值503 `demo_scope_conflict`。API/CLI共用resolver；resolver使用绑定引擎的独立只读连接，不开启业务Session事务，不提交写入。资源跨分区引用仍拒绝，Worker持久消息保持原分区。
- SPEC-061-003：新DDL无identity_users/identity_sessions及身份FK。两处created_by保留普通UUID避免旧库NOT NULL兼容问题；业务复合FK、唯一约束、预算、Outbox不变。业务为空且仍有旧身份表的Schema明确拒绝（含身份表空表）；唯一业务分区可复用历史UUID。本片不改变现有运行库。
- SPEC-061-004：CLI删identity初始化/重置和initialized_owner依赖，默认业务命令解析Demo分区；恢复验证在业务表写入后回滚，不创建身份。旧dump与新Schema不视为兼容，历史恢复用旧代码。
- SPEC-061-005：/events冷进入立即请求业务数据，不先验证会话；首页入口直达/events。页面没有登录/注册、用户信息、账户设置或退出；业务错误内联展示和重试，不跳/login。来源credentials和内容identity_basis不受影响。

## 4. Checklist 与验证

- [x] CHK-061-001：固定上述架构、精确文件和接口；前后端失败测试复现旧身份依赖。
- [x] CHK-061-002：删身份实现/配置/DDL与页面守卫，实际OpenAPI生成客户端无身份残留。
- [x] CHK-061-003：隔离新Postgres完整Schema、匿名读写、空/单/多分区、业务回滚及任务/预算回归通过；未触碰共享hotkey_test或业务库。
- [x] CHK-061-004：后端1092 passed/14 skipped、Ruff/format/mypy；前端95测试、lint/typecheck/format/build；实际OpenAPI连续生成一致。14项MinIO相关外部集成未执行，不计通过。
- [x] CHK-061-005：浏览器冷进入、匿名保存/刷新、桌面/390px和生产CSP nonce通过；测试主题暂停，无采集/模型调用。
- [x] CHK-061-006：台账/教程与实现一致，技术证据及旧库未改边界见Acceptance001；不关闭完整来源/模型/长窗产品AC。

隔离库名使用`hotkey_test_demo_<suffix>`，复用本机Postgres服务但只清空该测试库。消息/缓存测试只用唯一topic/group/key，不删除共享服务或数据。技术结果记录Acceptance001，M1真实来源与Plan058演示仍独立验收。

本片Demo代码/页面清理完成，证据为TECH-001-061。当前运行使用独立`hotkey_demo_20261001`空库验证，不切换旧运行库；新版dump/MinIO完整恢复和正式多用户权限未验，不属于本片完成结论。
