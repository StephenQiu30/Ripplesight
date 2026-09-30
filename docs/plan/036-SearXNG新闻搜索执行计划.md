---
layer: Plan
scope: issue
doc_no: "036"
title: SearXNG新闻搜索执行计划
status: completed
version: v1.1
date: 2026-09-30
owner: HotKey Team
canonical_path: docs/plan/036-SearXNG新闻搜索执行计划.md
prd: docs/prd/002-信息获取主链路需求.md
design: docs/design/002-信息获取主链路设计.md
source_task: 新增缺口；四关键词来源需SearXNG独立真实采集卡
architecture_prerequisite: "046 S03"
depends_on: ["031", "033"]
---

# Plan 036：SearXNG 新闻搜索

交付 `news_search` 从本机 SearXNG 的 `duckduckgo news` 入口到持久内容和缺口的链路。承接 FR-002-003、AC-002-002/004、NFR-001-101/102/105/106/111；SearXNG 进程健康不等于引擎有结果。

| SPEC | 实施路径与契约 |
|---|---|
| SPEC-036-API-001 | 修改 `backend/app/sources/adapters/web_search.py`、`connections/presets.py`；只请求固定端口 8888 的本机 JSON 搜索入口，宿主机为 `127.0.0.1`、Compose 为 `host.docker.internal`，固定 `duckduckgo news`，记录请求词、页号、实际引擎和 unresponsive/timeout 信息。响应有 error/失败引擎时不能因 results=[] 记成功空。 |
| SPEC-036-OPS-001 | 根 `.env.example` 与 `docker-compose.yml` 传入 `HOTKEY_SEARXNG_HOST`；仅允许 `127.0.0.1/host.docker.internal`，宿主机默认前者、Compose 默认后者。`web_search.py` 校验配置并由预设冻结到连接版本；适配器只接受所选主机的单项白名单、HTTP/8888/空基路径，不允许改端口、路径、凭据、query 或重定向。不新增表、HTTP DTO、模块或依赖。 |
| SPEC-036-DATA-001 | `content/discovery.py` 用来源原生 ID，缺失则规范 URL 构造稳定身份并记录依据；只去除明确追踪参数，保留有语义 query。发布日期与首次发现分离；摘要不是完整正文，内容版本保留字段可用性。 |
| SPEC-036-JOB-001 | `content/discovery_execution.py` 只在支持并有预算时翻页，页重复/无可信尾段/有限结果均保留缺口；同页重放不重复持久计量。适配器仅访问本机服务，结果链接不作为自动抓正文入口。 |

- [x] CHK-036-001 → API-001：扩展 `backend/tests/unit/test_keyword_search_adapters.py`，覆盖引擎失败与合法空、非 JSON、慢响应、重复页、没有 publishedDate。
- [x] CHK-036-002 → DATA-001/JOB-001：新增隔离的 `backend/tests/integration/test_news_search_replay.py`，验证 URL 身份、窗过滤、部分页入库、预算停止、重放和请求页数对账。
- [x] CHK-036-003 → AC-002-002/004：真实本机引擎产生可打开原帖，记录实际引擎与 JSON 结果、Job/内容版本/窗口；第二次扫描不重复身份。外部引擎不可用时来源保持失败并显示原因。
- [x] CHK-036-004 → OPS-001/API-001：分别从两种主机的预设构造真实适配器，受控 JSON 请求验证 `/search`、引擎和计量；未准入主机、端口/路径/query/凭据变体或不一致白名单被拒绝。真实 PostgreSQL/Kafka 重放继续核对身份、预算与部分覆盖。证据见 EV-002-054。

2026-09-30 容器入口修复范围：隔离 Compose Worker 对 `127.0.0.1:8888` TCP 连接失败、对 `host.docker.internal:8888` 成功；旧适配器和预设均固定容器自身回环地址。先保存三项失败回归，再按上述固定入口合同修复。此为 Plan058 扩围的运行准备，不发真实搜索请求、不提高已耗尽的每日预算；A 同主题短窗未通过前不开始 B。

运行 B 门禁；前端复用 041、覆盖复用 034。真实结果写 M1 Acceptance 的 Plan 036，不跨库拼接旧计数，不以 HTTP 200 关闭 AC；72 小时由 009。回退仅停本来源，无需更改其他来源配置。

## 阶段门禁

- [x] CHK-036-G0-001：核对046 S03、031/033技术产物和本机引擎配置。
- [x] CHK-036-G1-001：冻结API/DATA/JOB的实际引擎、错误、URL身份与分页边界。
- [x] CHK-036-G2-001：保存HTTP200但引擎失败、非JSON、重复页、预算耗尽的失败测试。
- [x] CHK-036-G3-001：完成CHK-036-001/002，部分结果和错误不伪装完整空集。
- [x] CHK-036-G4-001：运行B及真实PostgreSQL/Kafka计量重放。
- [x] CHK-036-G5-001：执行CHK-036-003真实本机引擎与原帖核对。
- [x] CHK-036-G6-001：登记AC-002-002/004的本来源结果；持续窗由009。

2026-09-27 技术、受控重放与两轮真实本机引擎证据见 Acceptance 002 EV-002-019。真实 MSN 抽样原帖可打开，前后两轮分别入库 7 条而稳定身份总数仍 7，实际引擎在 Job 检查点，尾段均为 `partial/unverified_terminal`。代码提交 `95c17f94` 的远端 backend/contract/runtime 均成功，backend **884 passed、8 skipped**，固定 `hotkey_test` 用例由远端覆盖，G4 通过。本卡按单来源边界 `completed`；父级四来源和连续 72 小时仍由 009 汇合。

2026-09-30 容器入口修复见 Acceptance 002 EV-002-054：两主机受控请求和真实 PostgreSQL/Kafka 重放 **2 passed**，来源/预设/Feed 单测 **113 passed**。提交 `278ee8b440caedbff3a51930ebb18201e6113365` 的远端 backend **1089 passed、8 skipped、2 warnings**，contract/runtime 均成功；CHK-036-004 与修复发布门禁通过，本卡恢复 `completed`。本轮没有真实搜索请求，Plan058 A 同主题短窗及 B 扩围仍待验收。
