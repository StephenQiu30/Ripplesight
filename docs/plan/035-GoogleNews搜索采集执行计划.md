---
layer: Plan
scope: issue
doc_no: "035"
title: GoogleNews搜索采集执行计划
status: in_progress
version: v1.0
date: 2026-09-26
owner: HotKey Team
canonical_path: docs/plan/035-GoogleNews搜索采集执行计划.md
prd: docs/prd/002-信息获取主链路需求.md
design: docs/design/002-信息获取主链路设计.md
source_task: 新增缺口；四关键词来源需Google News独立真实采集卡
architecture_prerequisite: "046 S03"
depends_on: ["031", "033"]
---

# Plan 035：Google News 搜索采集

交付 `google_news` 从主题词、搜索 RSS、持久帖子到可核对窗口的单来源链路。已有 `rss.py` 和开发库计数只作基线。FR-002-003、AC-002-002/004，NFR-001-101/102/105/107/111。

| SPEC | 实施路径与契约 |
|---|---|
| SPEC-035-DATA-001 | 修改 `backend/app/sources/adapters/rss.py` 和 `sources/contracts.py`：保留 Google News feed 原生 guid；缺 guid 时采用规范 URL 的明确 fallback 标识并保存身份依据。标题、摘要、作者、链接、published_at 和 observed_at 分开；缺作者/发布时间不造值，空简介不整页回滚。 |
| SPEC-035-JOB-001 | `content/discovery.py`、`content/discovery_execution.py` 将 source_key、固定连接/主题版本、请求词、24 小时默认/7 天最大窗口和页证据写入发现。源端搜索结果再经同一主题规则本地过滤；发布时间已知则按窗过滤，未知按首次发现入统计并标明。 |
| SPEC-035-SEC-001 | `connections/presets.py` 限定 Google News 入口和允许跳转主机；逐跳检查，不能为打开外部原帖放宽采集白名单。查询页面不发 RSS 请求。RSS 快照无法证明历史尾段，标部分/未知覆盖；合法空 Feed 和 XML 错误分开。 |

- [x] CHK-035-001 → DATA-001：扩展 `backend/tests/unit/test_feed_adapters.py`，覆盖无 guid、无时间、空摘要、重复 guid、不同帖子相同标题、HTML 字段与合法空 Feed。
- [x] CHK-035-002 → JOB-001/SEC-001：新增 `backend/tests/integration/test_google_news_replay.py` 并扩展 `test_keyword_search_adapters.py`，验证主题换版、窗边界、重复消息、失败保留已入库、重定向拒绝与预算截断；断言请求/页/内容/去重对账。
- [ ] CHK-035-003 → AC-002-002/004：用一个真实获准主题取得可打开原帖，保存 RSS 观察时间、Job、内容版本、首次发现与覆盖事实；再次扫描身份不重复。无真实命中则记录未通过，不能用受控 Feed 替代。

运行 B 门禁和上述测试；不新建专用 HTTP API，消费现有主题、Job、内容与覆盖端点。结果写 M1 Acceptance 的 Plan 035，真实证据保留来源失败和未知尾段；72 小时由 009，相关性由 040/005。失败停本来源调度，已有资料继续可读。

## 阶段门禁

- [x] CHK-035-G0-001：核对046 S03、031/033技术产物与Google News预设/白名单。
- [x] CHK-035-G1-001：冻结DATA/JOB/SEC的RSS身份、时间依据、窗与部分覆盖。
- [x] CHK-035-G2-001：保存无guid、重定向、半页失败及预算截断失败测试。
- [x] CHK-035-G3-001：完成CHK-035-001/002，入库与缺口、预算同账。
- [x] CHK-035-G4-001：运行B及真实PostgreSQL/Kafka重放验证。
- [ ] CHK-035-G5-001：执行CHK-035-003真实RSS→可打开原帖→二次去重。
- [x] CHK-035-G6-001：登记AC-002-002/004的本来源证据；72小时由009。

2026-09-27 技术与真实运行证据见 Acceptance 002 EV-002-018。RSS `SourcePost.identity_basis` 已进 `content_records`/内容读取 DTO；预设、工厂和适配器同用固定入口，Google News 拒绝重定向。受控 PostgreSQL/Kafka 测试核对版本、时间边界、重投、失败保留与预算；真实同主题两轮各保存 87 条，身份总数仍 87，来源/全局预算含一次上游失败各 3。代码提交 `06b47ca5` 的远端 backend/contract/frontend/runtime 均成功，backend **875 passed、8 skipped**；固定名 `hotkey_test` 用例由远端覆盖，G4 通过。当前浏览器打开抽样 Google News RSS 原帖链接返回连接关闭，CHK-035-003/G5 未通过。保持 `in_progress`，不据此关闭 AC-002-002/004。
