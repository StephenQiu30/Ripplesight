---
layer: Research
scope: shared
doc_no: "050"
title: AIHOT 全量源码与迁移覆盖矩阵
status: reviewed
version: v1.0
date: 2026-10-02
owner: HotKey Team
canonical_path: docs/research/050-AIHOT全量源码与迁移覆盖矩阵.md
reference_commit: 035f7b7f6e26cf203562ddd6065ff7adc1bb0c07
prd: docs/prd/046-AIHOT全量业务迁移需求.md
---

# AIHOT 全量迁移功能与验收矩阵

日期：2026-10-02。上游固定 SHA：`035f7b7f6e26cf203562ddd6065ff7adc1bb0c07`。只读源码：`/tmp/hotkey-aihot-20261002-01`。对照：HotKey `docs/research/049-AIHOT功能拆解与HotKey需求对照.md`。本矩阵仅据固定源码静态核对，未运行、安装或启动 AIHOT；代码迁移进度只见 BACKLOG，真实运行证据只见 Acceptance。

**最新范围取代先前研究中的“不迁入/可选/后置候选”范围判断：用户已明确要求全部功能迁入，包含六种来源、全部后台、阅读、报告、月报、通知、模型榜、Codex 公告、海报、SEO、RSS/API/MCP、反馈和运维。** Research049 的源码事实仍有效；其 §9.2、§9.3 的特有模块排除、可选增强与旧排期表述不能继续代表本次授权。完整迁移不等于原样复制 Node/Fastify/pg-boss/React Router、自动解禁外采/付费或用上游测试替代本地真实验收。

下文上游后端路径省略 `packages/backend/src/`，HotKey 现有领域路径省略 `backend/app/`。迁移类型：**资产**=可复制并改变量/品牌的数据或文字；**纯逻辑**=抽取后转 Python/现有前端；**业务移植**=接本项目状态、版本、事务、任务和合同；**边界修正**=上游欠缺或存在偏差，完整功能必须补齐。所有项均是待验收目标，不是已实现声明。

## 1. 事件优先：完整输入、输出与状态合同

### 1.1 上游真实模型

| 对象 | 精确输入/输出 | 迁入时的冻结要求 |
|---|---|---|
| ReportView | `title, source, firstParty, at:Date|null, summary:string|null, frame?:{subject,action,object,occurredAt}` | 绑定 owner/topic、content_id/content_version_id、分析与提示词版本、人工文字版本、来源参与模式及许可版本；未知时间保持空值 |
| CandidateView | `factId,storyId,factTitle,members,storyRoot,score,report` | 候选身份和代表证据版本固定；score只是召回强度；`storyRoot`来自当前可信根事实而非模型自由输出 |
| BatchSchema | `query:string<=400, decisions:[{id:string,relation,confidence[0,1],note<=400}]` | 候选使用 C1…Cn，校验ID来源；重复fact只取第一次；记录遗漏/非法字段，不能把解析失败伪装成模型可靠拒绝 |
| PairSchema | `a,b,difference:string<=400,relation,confidence[0,1]` | 完整两个代表报道，复核轮交换方向；模型/供应商是否不同要显式配置，上游默认不保证不同 |
| SignalSchema | `decisions:[{id,relation,confidence}]` | 讨论证据与报道成员分开，不能由信号单独创建事实/事件 |
| Relation | `SAME_OCCURRENCE / SAME_STORY / UNRELATED / ROUNDUP` | 同一次发生=同fact；直接发展=新fact进入同event；主题相同或公司相同不充分；盘点不能把多件事融合 |
| Verdict | `relation,confidence,note` | 写入模型原始答案、解析结果、输入指纹、receipt/call ID及规则版本，支持审计和重算 |
| GroupOptions | `signalOnly?,force?` | force只清自动归属和信号；人工归属优先；显式重新归组可解除“保持独立”覆盖 |
| GroupResult | verdict=`same-fact/same-url/new-fact-in-story/new-story/roundup/kept/standalone/manual/skipped/signal/signal-native/signal-unmatched/historical`，可有factId/storyId | 主决定与附带结果分开。consolidated/redirected/rematched/reclaimed及consolidationError/rematchError/reclaimError是可部分失败结果，不能抹掉已提交主决定 |

上游关系没有 `UNKNOWN`：`z.enum(...).catch("UNRELATED")`；不合法confidence回退0.5；遗漏候选补 `UNRELATED,confidence=0`。**预筛 PASS/BLOCK/UNKNOWN 是不同合同，UNKNOWN 继续处理。** HotKey现有二值prompt为“无法确认 same_event=false”，但调用失败/无效结构保留候选failed；迁移要区分业务不匹配、证据不足、解析降级、调用失败。若增加公开 UNKNOWN 状态，应同时改schema、提示词、归组策略与评测，不把它静默塞入上游四分类。

`ROUNDUP` 实际归组会创建独立story/fact并记roundup决定；`consolidate.ts`、相关链接排除以roundup为根的故事。不能写成“上游综述不创建事件”。

### 1.2 可安全抽取的具体算法

| 源码 | 纯函数/规则 | 固定输入验收 |
|---|---|---|
| `events/relate.ts` | `verdictsByFact` | C编号大小写/空白、重复ID、非法ID、遗漏候选；遗漏默认无关0，保留降级诊断 |
| 同上 | `sameOccurrence` | 只筛SAME_OCCURRENCE，先confidence降序，再召回score降序 |
| 同上 | `storyForDevelopment` | 只筛SAME_STORY且storyRoot=true，取召回score最高；A根→B发展→C发展不能经B串联入A |
| 同上 | `looksLikeRoundup` | 有候选且每个为ROUNDUP才true；零候选不能判盘点 |
| 同上 | `signalTarget` | 同发生优先，否则同故事且confidence>=0.8；无合格对象返回null |
| 同上 | `firmlyTied` | 同发生/同故事且confidence>=指定阈值才true；上游初判0.8、故事复核0.75，须保留方法版本并校准 |
| 同上 | `reportText`, `lexicalSimilarity` | 标题+摘要前300字符；去空白字符二元组交集/较小集合大小；它不是pg_trgm或cosine，不混用阈值 |
| `events/derived-content.ts` | `digestInputsHash` | 排序后材料ID/题/摘要/来源/firstParty/time构成哈希；顺序不改hash，文字/许可导致输入集合变化须改hash |
| `editorial/writing.ts` | `clampText`, `cleanArticleTextForLLM`, `compactAnswerFirstSummary`, `parseTranslateOutput`等 | 抽取文字处理，仍需适配AI实体词表、中文长度与输入类型；`enforceIdentity`不能丢失原文实体约束 |
| `scripts/eval-relations-core.ts` | `parseRelationGoldJsonl`, `sampleRelationGold`, `relationMetrics`, `storyTieMetrics`, `safeReportNamePart` | 重复case拒绝、日期/标签校验、先split后采样、相同seed稳定、错误独立计数，路径安全 |

文件整体有Zod/提示词加载/日期/DB或词表依赖，以上是抽取边界，不是“整文件无依赖可导入”。

### 1.3 归组和人工操作验收

| ID | 完整行为 | 关键状态/失败/并发验收 | 上游依据 |
|---|---|---|---|
| EV01 | 可信报道召回与代表证据 | 同URL、原生回复/引用优先；近14天发现的title+summary向量候选min0.6/top10，无向量词法min0.25；保留HotKey当前72h/pg_trgm合同直到正式方法变更，不静默混用两窗 | `events/recall.ts`, `events/group.ts` |
| EV02 | 同事实去重与直接进展 | SAME_OCCURRENCE进既有fact；cosine<0.85可复核；SAME_STORY仅根fact产生新fact；公司/产品重复但不同发生不得误并 | `events/group.ts`, `events/relate.ts` |
| EV03 | 稳定身份与修订保留 | 内容revision默认保留自动归属；人工独立/归属胜过修订及重试；模型事务外调用，提交锁材料与成员，再核revision/analysis/公开文字/mode/visibility/目标活动状态 | 同上 |
| EV04 | 历史、隔离与讨论材料 | historical不创建事件/信号；isolated跳过；hot_signal只连已有故事；原生引用优先；无向量无匹配，不能凭空创事件 | `content/materials.ts`, `events/group.ts` |
| EV05 | 后到原帖与信号重匹配 | 原帖到达后重新处理48h内等待引用/回复；新fact可重匹配近6h未附着讨论；已人工放置/拆离不自动再贴；无embedding重匹配停用且说明 | `events/group.ts` |
| EV06 | 跨故事合并、相关边 | 强连多个故事不能直接融合；分别直接比较根报道，两轮符合阈值才合入最早根；盘点排除；未合并时>=2篇独立联系报告可新增双向related边 | `events/consolidate.ts` |
| EV07 | 拆离/保持独立 | 删除fact membership及heat signal，落override理由/actor，刷新其他代表报道与派生文字；模型执行途中拆离，晚结果不得重新附着 | `events/corrections.ts`, `tests/events.test.ts` |
| EV08 | 合并/旧ID | 事实和信号搬到存活事件，重复信号一份，版本递增、旧publicID别名/重定向；重复操作幂等，自合并/不存在/已合并冲突；本地operation_id+expected_revision合同 | `events/merge.ts`, `events/corrections.ts` |
| EV09 | 显式重聚 | requestId单例；解除standalone但不解除manual membership；清自动归属与热度并失效派生内容；pending材料暂不做别人候选，失败继续pending，成功后再可作为证据 | `events/group.ts`, `database/migrations/0032_regroup_pending.sql` |
| EV10 | 指定fact移入与完整split | **上游缺失完整入口**。HotKey既定split必须实现：选成员、目标/新fact/event、操作理由、expected_revision、冲突409、排除约束、当前成员唯一归属、全部派生失效；旧标题不得残留被移走事实 | `events/corrections.ts`仅detach/merge/requestRegroup；HotKey Design004 |
| EV11 | 综述、最新进展与生命周期 | 输入hash/version，最多最新40篇摘要220；权限或文字改变先清公开旧digest/latest/事实frame并增加version；提交再核当前输入hash/version；active<24h/watching<72h/settled | `events/digest.ts`, `events/derived-content.ts` |
| EV12 | 部分失败与重试 | 关系请求失败允许材料独立阅读，Job失败可重试；主归组已提交后consolidate/rematch失败单独记录，重跑不重复买响应或创建成员；输入变化输出为standalone/冲突而非覆盖新状态 | `events/group.ts`, `jobs/events.ts`, `providers/receipts.ts` |

**真正架构决定：** HotKey现有Event/Member只有一层，不能只改prompt。需要在既有events领域中承接fact身份、fact成员/角色(primary/report/mention)、根事实及发展关系；Event继续作为story身份，避免两套事件主键/状态。每个读写均保持owner/topic边界。现有 `events/clustering.py`、`events/services.py` 的候选指纹、topic锁、expected_event_revisions、调用账本和Outbox可继续用；不能绕开它们引入上游全局SQL/pg-boss。

## 2. 六种来源、素材、分析与媒体：全量矩阵

| ID | 功能/用户操作 | 复用/移植源码 | 必要状态与验收 |
|---|---|---|---|
| SC01 | 来源目录/新建/编辑/启停/筛选/详情/手动抓取/试抓 | `sources/types.ts`, `sources/config-keys.ts`, `admin/sources.ts` | 新配置可校验、重复来源身份冲突、乐观version/reason/audit、runs与最近材料；试抓本地样本和会外采/收费的预览分别标识；已停用不继续新抓，不抹已有证据 |
| SC02 | RSS/Atom/RDF | `sources/rss.ts`，`tests/rss-conditional.test.ts`,`rss-xhtml.test.ts`,`rss-links.test.ts` | 解析作者/时间/摘要/正文/媒体；ETag/LastModified绑定configHash及最终重定向；304不丢cursor；配置/目标改变不能用旧304；短正文/teaser进入待提取；Atom updated不得静默冒充HotKey原始publish |
| SC03 | 网页列表与详情规则 | `sources/web-list.ts`, `docs/examples/sources/news.html`, `tests/source-rules.test.ts` | CSS/Markdown/Docusaurus、URL允许/排除、详情title/date/excerpt、列表后不覆盖已确认详情title；不可实现配置拒绝而非忽略；detail上限、失败保存发现、付费Jina需准入 |
| SC04 | JSON/API/内嵌JSON列表 | `sources/json-list.ts`, `docs/examples/sources/news.json` | dot字段、URL模板、GET/POST、日期单位、过滤、缺字段/无效日期、受保护跨域跳转；声明实际分页范围，不称全历史完整 |
| SC05 | X搜索/账号分片/引用/Article | `sources/x.ts`, `providers/socialdata.ts`, `tests/x-shards.test.ts`,`x-article.test.ts` | 原生ID、水位、backlog、页预算、分片重放、跳过原生转发、正文/quote/raw媒体；官方X现有入口与SocialData可选供应商通过统一能力合同，默认关闭未准入供应商，不能重复采/收费 |
| SC06 | 微信公众号 | `sources/mp.ts`, `providers/dajiala.ts` | 最近列表每次<=8新文，首轮7天，正文重试<=3且发现3天内，列表/正文分开receipt，水位只在入库后推进；表明有限首页，超时unknown与预算延后；有正文不等于公开许可 |
| SC07 | 外部批量摄入 | `ingest/items.ts`, `apps/api/src/routes/ingest.ts` | token>=16且拒绝占位值、每IP10/min、batch<=50，返回逐条接收/跳过结果；新来源isolated、写入身份/来源/时间/许可校验；不是匿名正文上传 |
| SC08 | 到期调度、自适应频率与覆盖 | `sources/collect.ts`, `jobs/sources.ts` | source runs ok/failing/cursor/pending/failCount/nextFetchAt；默认40 due/concurrency8，X/MP2；部分入库幂等重放；budget延后不当source错误；自适应产出规则作为受准入上下限控制的功能，不能自动改宽HotKey风控/coverage合同 |
| MA01 | 统一发现身份、修订与多来源 | `content/materials.ts`, `tests/materials.test.ts`,`core-collection-identity.test.ts`,`core-collection-tail.test.ts` | 原生/URL身份、discovery与owner source分离；并发同URL一材料，标题正文excerpthash变化revision；旧hash回归、字符损坏不伪造新修订；HotKey评论父链/热榜快照继续原入口 |
| MA02 | 时间、历史与新旧材料 | 同上 | published/discovered/timeline/backfill保留；未来>discover+1h拒绝、晚到>48h历史；首轮近期backfill可建event/heat但不通知/报告；不把今天入库称今天发布；HotKey时间合同映射明确 |
| MA03 | 正文提取和质量 | `content/extract.ts`,`content/markdown.ts`,`content/sanitize.ts` | pending/ok/unconfirmed，Readability>=200字符，Jina/XArticle限定路径；抽取失败保留材料；清洗白名单、跟踪图片去除、Markdown保留结构、无确认正文不生成全文模式 |
| AI01 | 预筛/主题相关性/精选分离 | `editorial/analyze.ts`,`industry/selection.ts`,`industry/prompts/` | PASS/BLOCK/UNKNOWN与相关性/精选分别记录；缺证据BLOCK→UNKNOWN；评分2次同模型分别receipt、平均sum比较门槛，不能当独立供应商；tier不参与时不评分；HotKey相关性不被精选替换 |
| AI02 | 结构化、中文标题/摘要/理由/标签 | `editorial/input.ts`,`writing.ts`,`vocabulary.ts`,`industry/taxonomy.ts` | classification/tags/entities/fact frame/schema，实体白名单与identity guard，空材料/verbatim、首图失败纯文字回退、结构与评分并行；当前输入revision/标准/prompt/model版本冻结，旧答案不得改新材料 |
| AI03 | 多能力模型配置与成本诊断 | `editorial/models.ts`,`admin/models.ts`,`providers/llm.ts`,`providers/embeddings.ts` | 11能力override→env→default，能力兼容/vision校验，用量/失败/unknown/价格/来源；历史不自动重判；普通可评分链约5LLM次，embedding/关系/综述/报告/译文另计；模型供应商依既有ai授权 |
| AI04 | 全文与引用帖翻译 | `editorial/translate.ts`,`tests/translate.test.ts`,`translate-shutdown.test.ts` | selected/public/licensed confirmed正文才做；3500char批、60k cap，shield/unshield媒体/代码/链接；块错配二分一次，坏占位再试后保留原文partial；原文/译文版本一致；引用tweet+hash共享；读取不实时调模型 |
| AI05 | 精选/关系评测与后台比较 | `scripts/eval-selection.ts`,`scripts/eval-relations-core.ts`,`admin/selectbench.ts` | own gold/split/stratum/seed，TP/FP/FN/TN/P/R/F1/误选漏选分歧、threshold40..90 step2、用量耗时错误；either/错误单列；两个人造示例不作验收集；JSONL导入/去重/同样本比较和错误行提示 |
| ME01 | 签名图片代理/响应式尺寸/缓存/动图 | `media/images.ts`,`imgproxy.ts`,`renditions.ts`,`prepare.ts`,`apps/api/src/routes/media.ts` | HMAC签名/expiry/URL校验、URL+mode缓存及并发下载合并、失败短缓存、byte/pixel限额、ICO/头像裁剪/动图后台转WebP；新稿预热，失败可回原图且不阻正文；无跨租户任意URL代理 |

## 3. 热度、阅读、发布、报告和分发验收

| ID | 功能/操作 | 源码 | 必须验收的状态与边界 |
|---|---|---|---|
| HE01 | 独立参与者关注热度 | `events/hot.ts`, `tests/events-oss-heat.test.ts` | 48h窗，按当前group→owner→source去重，取last证据，Σ2^(-age/24h)，显示round(raw×100)/10；重复重采不增，但新篇刷新last；至少2且1editorial；top10、代表一手/精选/分数 |
| HE02 | 同群比较/趋势/快照/解释 | 同上 | 6h前可比cohort，新增/behind来源排除，unknown不是跌热；pct>10 up/<-10 down；new/surge/rising不同徽标；小时complete与48h补齐、30d保留、读时撤回过滤。关注热度与HotKey互动热度分别命名/版本，不覆盖既有统计 |
| RE01 | 精选、全部、筛选与阅读组 | `publication/timeline.ts`,`groups.ts`,`followups.ts`；web home/all/item/story | 精选与全部/未分析/被预筛/未知不同；分类/标签/官方/news/X，fact折叠多个出处，稳定代表anchor、后续发展；列表/详情正常空加载错误忙/未授权状态 |
| RE02 | 原文/中文/摘要/全文/目录/媒体/Markdown/海报 | `publication/detail.ts`, `apps/web/app/features/item/` | 没全文许可或质量不足仅摘要；原文与译文切换、目录引用/quote/来源；撤回/纯signal无公开页；summary-only去掉不准正文/理由等；读取零模型调用 |
| RE03 | 文本搜索 | `publication/pool.ts`, web all/search-busy | 标题摘要与许可正文、<=6词AND、title6/direct3/body1，相关/时间两tab，40/page最多50page、concurrency4/wait8/3s忙503 RetryAfter5；现有owner/topic/来源/时间过滤且无跨分区结果；不是RAG |
| RE04 | 策展主题页 | `publication/topics.ts`,`industry/topics.json`,`industry/taxonomy.ts` | company/field/genre、tags/related、排序、薄页面noindex门槛；与用户监控规则分别识别，编辑监控规则不会改历史内容版本 |
| RE05 | 本机收藏/已读/导入导出/主题与草稿 | `apps/web/app/lib/local-state.ts`, web starred/more | 收藏500/已读5000/导入2M/version1/合法ID日期；合并导入不覆盖既有收藏、跨tab/WebLocks、stable snapshot、SSR/隐私模式/存储坏数据/空间不足；保留本机性质，不承诺跨设备账户 |
| PU01 | 单一可发布投影 | `publication/publish.ts`,`rules.ts`,`scope.ts`,`items.ts` | 原材料+当前分析+override+归属→唯一projection；pool/editorial/pass/title+summary；精选额外judgedSelected/tier；source暂停保留，mode/许可变更重投影；public/summary-only/withdrawn；禁止第二事实库 |
| PU02 | 归组释放门、同步ledger | 同上及 `publication/v1.ts` | 列表等待归组或可配180s；具体URL不都等待；selected epoch/seq/upsert/remove，cursor绑定筛选、old epoch409重建snapshot；当前snapshot不限items列表7d；URL-only修订也入变更，未变重发不改freshness |
| PU03 | 出口撤回/授权/缓存 | `publication/availability.ts`,`links.ts`,`stories.ts`,`reports.ts`, `lib/cache.ts`,`lib/cursor.ts` | site_fulltext与syndicate_fulltext分开；所有新的网页/API/RSS/Markdown/MCP/图像读取核许可撤回；ETag包含可见性/版本；失效缓存或明确TTL。已下载/订阅副本/local收藏不承诺远程清除 |
| RP01 | 日报 | `reports/compose.ts` | 上游08h [D-1 08,D08)、selected/public/非backfill，归刊max(timeline_at,visible_after)，同fact优先一手/高分、前7期抑制、8/cat+12flash、30项导语。HotKey现有自然日09h/程序数字/模板降级保留或显式改刊期版本，不混口径 |
| RP02 | 周报、月报、补刊与修订 | 同上 | 完整ISO周/完整月，40/60候选，<=6theme×8真实引用；周一10h/月1日1030上游时间与本地正式刊期映射；自动不覆盖旧刊、reason+expectedRevision+reportRevisions、每轮有界8缺刊；空刊失败/模板降级区别明确 |
| RP03 | 报告输入、旧文和撤回 | 同上及 `publication/reports.ts` | **上游saveReport只检查报告行revision，不完整核候选版本。** HotKey必须freeze材料/许可/分析输入提交再核，撤回/纠错使含旧事实的lead/overview/theme prose失效或重写，不仅过滤引用数组；所有出口同修订 |
| RP04 | 刊物阅读与归档 | web report-latest/report-detail/daily-archive、`publication/reports.ts` | 最新刊、前后期、日历/月归档、每日/周/月历史key、打印/Markdown/分享；缺刊、正在生成、已撤引用和空内容明示，不写不存在的报告订阅功能 |
| NT01 | 精选与Codex内容通知 | `notify/selected.ts`,`selected-content.ts`,`deliver.ts`,`feishu.ts` | public/selected/非silent/非backfill/<=12h，source+target enabledAt、release gate、10min同题lease、target×fact/article幂等、siblings去重、每镜像前再核权限版本；卡片引用原文与站内，关闭target不补推旧稿 |
| NT02 | 投递unknown与人工恢复 | `notify/deliver.ts`, `admin/runs.ts` | pending/sending/sent/failed/skipped/unknown；15min残留sending→unknown，pending→failed；timeout不可自动重复；version+note人工确认/放弃/重发；重发仍过业务资格；已有HotKeyexecutor承接 |
| NT03 | 现有HotKey报告通知/Obsidian | HotKey `reports`/`knowledge`/`notifications` | 属本项目既有完整链路继续保留，AIHOT没有SMTP/报告订阅模板底座；不能因全迁移删除本地已有导出、任务与模板降级，也不能声称上游已提供这些功能 |
| OUT01 | 公开REST全接口 | `apps/api/src/routes/v1.ts`, `publication/v1.ts` | items/hot/story/daily/weekly/monthly/codex/selected snapshot+changes；items24h/7d、limit<=100、cursor/Problem/400/404/409/503、ETag/Cache/CORS/方法限制；FastAPI定义唯一OpenAPI生成客户端 |
| OUT02 | RSS全种类 | `publication/feeds.ts`, `apps/api/src/routes/feeds.ts` | selected摘要/full/all/category/fullcategory/daily；全文再分发白名单，否则退摘要；XML escaping/stable GUID/pubDate/撤回过滤/签名图片期限、条件304 |
| OUT03 | Agent Markdown/单篇Markdown | `publication/agent.ts`,`llms.ts`, `apps/api/src/routes/agent.ts` | guide/latest/search/hot/story/daily/date/codex；单篇出口另读detail许可；外部材料不作指令、引用链接、escape、正常错误明确；现快照没有周月Markdown，若补充属于本地扩展 |
| OUT04 | MCP五工具 | `apps/api/src/routes/mcp.ts`, `packages/contracts/src/mcp.ts` | get_latest/search/get_hot_topics/get_story/get_daily，readonly/stateless StreamableHTTP、24h/7d/limit1..30、搜索selected无结果才all、hot10/story50、host/origin/CORS/abort/关闭/缓存；固定快照5工具，线上宣传8不作为已开源验收 |
| SEO01 | SEO/站点静态发现 | `publication/sitemap.ts`,`llms.ts`,`site/meta.ts`, web seo, `apps/api/src/routes/static.ts` | canonical/meta/JSONLD/sitemap/robots/llms/manifest/security/contact与内容政策页；默认noindex薄/非可索引/私人页；indexable需public+summary+许可政策；IndexNow显式启用/水位/失败不推进 |
| SEO02 | OG/单篇海报/报告主题事件分享图 | `publication/og.ts`, `apps/api/src/routes/og.ts` | site/pages/items/posters/reports/topics/stories PNG；输入版本/授权/canonical/短数据投影、分享图不多读全文；海报原品牌/名牌需换HotKey；字体另守OFL、图片缓存失效与错误回退 |

## 4. 模型排行榜：全部特有能力正式纳入

| ID | 功能/状态/操作 | 具体复用资产与算法 | 验收条件 |
|---|---|---|---|
| LB01 | 评测来源注册/目录/协议与抓取 | `leaderboard/source-registry.json`,`registry.ts`,`directory.ts`,`fetch/index.ts`与`fetch/sources/` | 全部10fetcher：ArtificialAnalysis、Arena、LiveBench、EQBench、Epoch、DeepSWE、TapTap、Mercor、Vals、TerminalBench；同fetcher多sourceKey不遗漏；API/CSV/HF/GitHub/zip解码有界及署名license |
| LB02 | 原始配置与模型身份 | `fetch/configuration.ts`,`identity.ts`,`store.ts`,`rank.ts` | source aliases→canonical model/slug；未登记新模型可建identity但不自动认定权重/官方/价格；匿名cloaked排除；代表配置依优先级/firstParty/固定名称排序而非挑最高分；重复配置保留原表先出现记录 |
| LB03 | 不变快照/失败沿用/保守解析 | `fetch/refresh.ts`,`fetch/store.ts` | unchanged只更新lastSeen；内容hash变化新snapshot+raw配置证据；新解析0行或骤减<上一半拒绝；抓取两路并发、存储按registry顺序；单来源失败用上一份并显式陈旧，不推导覆盖成功 |
| LB04 | v15计算/资格/固定预算 | `method/v15.ts`,`method/inputs.ts`,`method/kemeny.ts`,`method/ndtr.ts` | 预算broad.30/preference.10/专业.60及各子预算；缺来源份额不重分；HIGHER/LOWER，发布误差软比较2Φ(Δ/SE)-1否则sign；overall至少3sources/families/operators/categories+2directAnchors；18月发布窗，未知日期保留；7日同协议carryforward，较新排除不复活旧分 |
| LB05 | Kemeny/得分/敏感性 | 同上 | 加权不完整排序，lazy三角约束/force反排/确定tie，solver optimal/lowerbound/gap；分数是固定anchors下排序支持index，不叫能力距离或校准胜率；drop operator/unit、weights±20%、ordinal敏感性及unknown/incomplete展示 |
| LB06 | round发布/旧榜持续可读 | `method/run.ts`,`compute.ts`,`compute-worker.ts` | published/refreshed/unchanged/failed；fingerprint绑定method+board输入，数据验证时间/汇率单独refresh不重求解；公开overall至少10models/8anchors，category5/4，连通且optimal才publish；任一公开榜失败整轮保留上一published；CPU计算隔离不能阻塞API |
| LB07 | 榜单/分类/模型详情/规则/来源说明 | `leaderboard/read.ts`,`access.ts`, web `leaderboard*.tsx` | overall/coding/aesthetics/reasoning/knowledge/writing/professional方法与可发布榜不同；站点必须依据已有published结果展示；国内厂商+开放权重组合先完整排名后筛前30，rank/score不重算；保留源排行/配置/证据/稳定性 |
| LB08 | 官方权重/价格/汇率/名录 | `model-weights.json`,`prices.ts`,`database/seeds/lb-models-2026-09-29.json`,`lb-official-prices-2026-09-26.json` | 精确型号官方权重、许可链接，厂商国产判断不等于可国内使用；API价格单位/日期/source、USD/CNY quote证据；调价导入不得把旧价格当即时最新；种子可复用注明时间与来源，不执行上游seed脚本 |
| LB09 | 四次刷新及首轮 | `apps/worker/src/schedules.ts`,`apps/worker/src/main.ts` | 0205/0805/1405/2005检查；无初始published启动排一次；collect关闭仅stored快照计算，key未准入该来源不可请求但份额保留；算法方法变化同步rules并升version |

纯逻辑候选包括 `categoryPolicy/netMatrix/computeBoard`、`reversalCost/solveKemeny`（后者依HiGHS）、`modelSlug/cloakedModel`、`storedConfigurationKey/selectRepresentatives`、配置priority/源rank/资格等。**架构决定：Python需要等价HiGHS求解器及CPU隔离，不能偷换成平均分/启发式排行且仍称v15；新增依赖与方法tiePolicy必须定标。** 上游JS的solver及worker不直接引入HotKey后台。

## 5. Codex公告监控：不是本人额度查询

| ID | 功能/状态/操作 | 源码 | 验收条件 |
|---|---|---|---|
| CX01 | 固定作者采帖/上下文/水位/backlog | `monitor/scan.ts` | @thsottiaux，normal5min/hot3min，tick1min，lookback48h，普通新页最多5+backlog最多5，最多2级回复/引用；原生转发不当作者声明；过期opaque cursor可按beforeId补max_id，缺口不能算verified |
| CX02 | 命题识别与忠实翻译 | `monitor/recognize.ts` | relevant/outage/recovery/needsReview、direct_reset/reset_credit、announce/progress/confirm/amend/withdraw、real/count/relatesTo/excerpt/statedTime/scope/expectedLanding；原文引用校验、数量必须原文明确，条件/玩笑/机制描述不生成承诺 |
| CX03 | 程序状态机/合并数量/防假确认 | `monitor/assemble.ts` | announced/confirmed+withdrawn，source_post/receipt_review证据区别；疑义或excerpt不在post→held，不改publicfacts；同帖重复命题不额外造事件；progress未完成，confirm只能从证据转状态，确认时间是发帖时间不是精确到账 |
| CX04 | 时间换算与估计标签 | `monitor/time.ts` | `pacificToUtc/resolveStatedTime/scheduleFrom/estimateFor/manualSchedule`可移植；America/Los_Angeles DST、跨午夜/dayOffset/relative/deadline/window；来源时间和模型/history估计区别、模型窗<=36h且不早于宣布/不矛盾；用Pythonzoneinfo对齐DST歧义 |
| CX05 | 顺序、恢复与verified | `monitor/scan.ts` | oldest待处理失败后后帖等待；backlog存在不解释前端新帖；即使collection失败仍处理已存稿和欠推；processed/needsReview/held/backlog全清才能lastVerifiedAt；session锁防并发、网络/模型不持事务 |
| CX06 | 页面/日历/公告快照/版本探针 | `monitor/read.ts`,`publication/monitor.ts`, web codex-reset, site/v1/agent routes | 按日历史、当前公告/活动/故障与source链接，watermark/freshness/unknown；ETag/version随人工修改更新；无key/未启用状态不能包装为“已监控暂无公告”；不读取用户真实额度 |
| CX07 | 人工审查/修订/回执确认/撤回恢复/改归属 | `admin/monitor.ts` | updated_at version冲突409、理由audit；skip/reviewed、patchscope/time/type/status、reopen清confirmed fields，receipt_review不降级已有source_post；relink两事件version变化，人工审查不自动再调模型 |
| CX08 | 公告/确认/修订/撤回通知 | `monitor/scan.ts`,`notify/deliver.ts` | 欠推和recognition同事务写，36h过期不补；每post/target一张，amend/withdraw只告知原announce已送对象；unknown仍人工处理，重放不多推 |

## 6. 全部后台、反馈、任务与运维

| ID | 用户/运维操作 | 源码 | 状态与验收 |
|---|---|---|---|
| AD01 | 后台导航/概览/来源/内容全链/审计 | `admin/navigation.ts`,`sources.ts`,`content.ts`,`audit.ts`,`apps/web/app/routes/admin/` | 来源runs/cursor/health；内容discoveries/revisions/extract/analysis/calls/group/publication/ledger/deliveries；筛选/分页/错误态，reason/actor/expectedversion，敏感credential不入DTO/日志 |
| AD02 | public/summary-only/withdrawn及SEO/字段override/清覆盖/重跑 | `admin/content.ts` | 文字/selected/silent/tags/reason override与materialversion，clear字段可恢复自动值；重跑extract/analyze/group带requestId，人工更改与慢model冲突；权限改变原子清派生文字，撤回可恢复但不重复旧推 |
| AD03 | 运行/unknownreceipt/delivery/requeue | `admin/runs.ts`,`operations/recover.ts` | 运行queue/失败/heartbeat/来源lag、received结果复用；人工release需要查账billed+note；投递unknown需核对送达并expectedversion；已完成不重复恢复，事务后崩溃可从持久audit续唤醒 |
| AD04 | 全模型/预算/目标/联系二维码/SelectBench | `admin/models.ts`,`settings.ts`,`selectbench.ts`,`site/contact.ts` | capability有效/兼容、reset override、rate预算、启停目标enabledAt/reason、二维码限格式大小并原子写；模型切换不重判历史；SelectBench import有格式错误输出 |
| AD05 | 后台准入与会话 | `admin/auth.ts`,`apps/api/src/routes/admin-auth.ts` | 上游密码/FeishuOAuth/白名单、signed state、safeReturn、persisted hashedsession30d/UA绑定/CSRF/登出/限频/credential轮换session撤销。**与现有Demo无产品登录冲突需明确产品模式/部署边界**：不能无说明恢复账号骨架，也不能将未来外网后台全匿名暴露；能力须有本地等价访问控制验收 |
| FB01 | 匿名反馈文字/邮件/页面/截图/草稿 | `operations/feedback.ts`,`apps/api/src/routes/feedback.ts`, web feedback | 字段验证、honeypot、5/min/sourceHash、封禁、截图格式/大小、提交确认/错误、敏感IP不存原文；内部Feishu关闭可暂存，失败forwarderror并可重试 |
| FB02 | 反馈管理/封禁/去除/截图访问 | `admin/feedback.ts` | new/triaged/replied/resolved/spam、version+note、搜索分页、ban/unban、erase联系内容/附件、审计；外部截图不可匿名读；数据保留与privacy文案一致 |
| OP01 | 统一任务/持久调度/停止/补任务 | `jobs/*.ts`,`apps/worker/src/schedules.ts`,`lib/shutdown.ts` | 10业务handler与全部cron映射下方附录；原子业务+Outbox，singleton/idempotency与typed payload，retry/expire/queued stale、cancel/shutdown不再发送下一paidrequest且保存已返回响应；沿用Kafka不新建pg-boss |
| OP02 | 供应商回执、预算与成本 | `providers/receipts.ts`, 其余providers | logicalkey绑定service/model/purpose/input/prompt/config/attempttag，pending+attempt先落、received先存raw、completed业务完成，received/completed复用；failed与unknown区别；滑动min/hour/24h每次attempt计数、缺budget上游放无限不应继承，金额硬上限用本地合同 |
| OP03 | 未知恢复 | `operations/recover.ts` | pending10min→unknown；上游unknown30min自动release一次未查账，再unknown人工。迁移保留完整诊断/人工恢复，并把自动重收费功能放显式策略与已授权预算下；默认暂停/额度不明不得放行；投递unknown没有自动重发 |
| OP04 | heartbeat/watch/健康/告警/摘要/来源周报 | `operations/heartbeat.ts`,`watch.ts`,`alerts.ts`,`reports.ts` | API watchdog监worker，来源失败/新稿积压/模型熔断/预算/榜单/monitor/备份/unknown；now/today/digest去重限频、恢复消息、quiet窗口/全开关；0900有事项才digest、每周sourcehealth；真实channel仍按启用条件 |
| OP05 | 备份/文件一致性/上传/保留 | `operations/backup.ts`,`retention.ts`, `tests/backup-files.test.ts` | pg_dump custom及清单核验、文件打包变化重试、上传对象store签名、部分DB成功files失败独立记录、3份local、陈旧告警；每日清缓存与普通run30d/failed90d；必须恢复演练与schema版本匹配，上传不等于恢复验收 |
| OP06 | source icon/site stats/static assets/部署开关 | `sources/icons.ts`,`site/stats.ts`,`config.ts`,`industry/features.ts`,`apps/api/src/routes/static.ts` | icon检查/回退/cache、站点stats/changelog/about/terms/privacy/security/manifest/contact，FEATURES开关一致关闭UI/routes/schedules；全部启用范围但未准入网络能力显示未启用，不能假数据冒充成功 |

## 7. 必须明确、不得由移植悄悄改掉的架构选择

1. **事件层次与修订：** fact归属、story根、split/move、source信号和owner/topic的SQL约束如何并入现有Event领域；不创建第二套稳定事件身份。
2. **部署与后台准入：** 公共匿名资讯读取、私人监控主题、本地Demo无登录与外网运营后台访问控制如何分层；完整后台需求不等于授权匿名改全站或回滚既定无登录模式。
3. **来源供应商：** X官方入口（本项目不迁入SocialData）、MP Dajiala、困难页Jina与已有Firecrawl的统一能力映射/预算。完整功能可以实现适配器并默认disabled，真实请求须有凭据、范围、许可和预算。
4. **模型与召回：** Codex app-server现有唯一调用账本能否支持所有capability/视觉/embedding；需要不同provider能力时显式注册，不直接恢复上游自动费用。当前pg_trgm/72h与上游embedding14d分别版本化，不能混称等价。
5. **榜单求解器与CPU隔离：** Python等价HiGHS、确定tie、300s默认限额与敏感性多轮求解资源；算法变更升methodversion及rules。不得引入JS后台sidecar来绕过固定栈。
6. **日/周/月刊口径：** 新月刊必须正式定义key/window/时区/计划；现有HotKey日报自然日09h与上游08h publicationcalendar不静默替换；报告输入必须冻结提交再核。
7. **统一公开范围：** 监控材料哪些经显式授权成为publication，谁能编辑/撤回、跨分区cursor与缓存；FastAPI/Pydantic唯一OpenAPI，不拷手写reference JSON当第二合同源。
8. **预算unknown策略：** 全量恢复UI/状态迁入，上游一次自动重收费不能违反既有禁止付费/不明结果不自动重发；缺预算默认阻断，实际金额和ratecap均可追溯。
9. **媒体/海报/对象存储：** Python清洗/Readability/图像编码/OG渲染采用何运行依赖、字库与cache位置，签名/SSRF/byte限额，以及当前对象store与恢复方案；不直接搬Sharp/Satori Node后台。
10. **许可与品牌：** 保留完整MIT版权/许可文本、固定SHA及复制清单；AIHOT name/logo不授权，字体OFL及第三方marks/数据各另守条款；代码MIT不授予新闻全文/再分发权。

## 8. 完整验收的最低证据组合

每功能至少记录：上游固定文件/规则→本地既有领域→合同差异→固定输入纯逻辑结果→数据库事务/版本/恢复验证→API及生成客户端→实际用户操作。优先复用上游故障场景，不能只复用成功路径。

关键跨功能场景：同URL并发；同事实十篇折叠但直接进展可见；内容新revision与分析/译文/归组慢答竞态；模型运行中人工拆离/合并/split；收到供应商答案但业务提交前重启；收到未知付费结果绝不擅自重发；通知sending重启变unknown人工核对；来源从editorial改isolated/全文许可撤销/材料withdrawn，全部新出口与缓存及报告文字一致；榜单来源半数解析/单来源失败/solver非optimal保留旧榜；Codex quote不在原文/needsReview/backlog未清不能确认或显示verified；本机收藏导入坏数据/跨tab并发；恢复备份和文件完整性。

仅离线或stub完成时应标“代码/合同验证”，不得填供应商、模型质量、浏览器验收、72h完整性、真实投递、冷启动或恢复演练已通过。未准入连接保留完整adapter/状态/UI，但验收记录应明确“实现已验证、真实provider待授权”，而非功能静默遗漏。

## 9. 必需功能实体与输入输出映射

以下是必须承接的**功能实体**，并不要求照抄上游表名。已有HotKey实体优先增加受控字段/相关记录；新业务实体在唯一 `backend/database/schema.sql` 中按本项目规范定义。不能把上游migration或seed脚本应用到现存业务库。

| 领域 | 必须承接/扩展实体（上游表） | 最小完整输入→输出与版本 |
|---|---|---|
| 来源 | 现有source/connection/configuration/job覆盖 `sources/fetch_runs/ingest_events` | kind/config/capability/mode/tier/firstParty/许可/interval/version→来源详情、cursor/backlog、lastAttempt/lastOK/health、fetchRun逐步结果与coverage；凭据仅配置引用 |
| 材料 | 现有content/version/observation覆盖 `articles/article_revisions/article_discoveries` | source/nativeID/URL/题/正文质量/时间/raw/hash→contentID、immutable version、发现关系、body状态、processing状态/error/retry/queuedAt；加入source用途与许可版本 |
| 分析与翻译 | 扩现有annotations/ai calls；承接 `analyses/translations/translation_attempts/quote_translations/editorial_overrides` | frozen version+prompt+model+sourcefacts→预筛/评分两次/精选/结构/题摘要理由标签/factFrame/原答；译文按材料revision及quoteID+textHash，translated/partial/skipped及失败次数；override带reason/actor/版本 |
| 精选/关系评测 | 新 `selectbench_runs/selectbench_results` 等价实体 | label/split/seed/sample/model/prompt/gold输入→摘要指标/每case decision+score+error+receipt+stratum；唯一run/model/case，允许可重复定位上游响应 |
| 事件 | 扩现有events/event_members/candidates；新增fact相关实体承接 `facts/fact_articles/grouping_decisions/grouping_overrides/regroup_pending` | frozen report/candidates/version→factID/eventID、role、manual、decision+relation+confidence+receipt、pending/failed等；根事实与直接发展关系；manualsplit/move版本审计 |
| 事件派生 | `story_aliases/story_links/story_digests/story_signals/hot_rankings/story_heat_hourly` 等价实体 | 成员和信号/输入hash/方法version→alias、相关边、digest/latest/active-watch-settle、参与者贡献、rank快照/complete/cohort；所有文字依赖ID/hash及版本可失效 |
| 发布 | 新统一投影承接 `publications/pool_search/selected_state/selected_ledger` | contentVersion+analysis+override+sourceLicense+fact/event→public/summary-only/withdrawn、eligible/selected、title/summary/reason/category/tags、source/url/times/bodyMode/syndicate/indexable/gate/SEO及projectionRevision；epoch/seq/hash/upsert-remove/watermark；搜索可用同投影索引，不能第二内容身份 |
| Feed/MCP/SEO | **无需独立feed/MCP事实表**；使用publication/report/leaderboard/monitor的读取投影；有IndexNow水位/配置 | query/window/category/cursor/ID→XML/Markdown/DTO/ToolResult/PNG及ETag/cache/nextcursor/problems；公开范围和授权统一，接口文档来自运行FastAPI；主动订阅管理上游未有，不凭全迁移造假实体 |
| 报告 | 扩 `reports/report_revisions` 本地等价实体及输入依赖 | kind/key/window/frozen输入+expectedRevision+reason→content{lead/overview/theme/refs/程序统计}/revision/model/call/origin/generationStatus；新增monthly，输入身份/hash与许可必须完整存证、失效与重新生成 |
| 模型名录 | 新 `lb_models/lb_aliases/lb_prices/fx_rates` 等价实体 | sourceAlias/baseName/provider/releaseSource→stable modelID/slug；精确权重映射与国产归属可配置文件；price{kind,currency,in/out/cache,verifiedOn,url}、FX{pair,date,rate,source}，价格不进ranking |
| 模型评测 | 新 `lb_snapshots/lb_scores` 等价实体，registry可版本化配置资产 | FetchResult{sourceKey/sourceURL/license/attribution/publishedAt/metadata/rows}→snapshotID/hash/fetchedAt/lastSeen/rowcount；rows保留model/configkey/kind/priority/selectedReason/metric/rawScore/bounds/sourceRank/sampleSize/rawSourceName/protocol |
| 排行轮次 | 新 `lb_runs/lb_rankings` 等价实体 | methodVersion+exactsnapshotIDs+boardinputs/fingerprint→run{published/failed/shadow/historical,summary/timing/evidence}；RoundResult published/refreshed/unchanged/failed；board{entries rank/score/coverage/stability,solver optimal/bounds/gap,comparisons/connectivity/budgets}；唯一run/board/model |
| Codex公告 | 新 `monitor_posts/monitor_events/monitor_event_posts/monitor_state` 等价实体 | post{id,author,time,text,url,raw/context}→recognition/translation/receipt/processed/activity/outage；propositions→event{type/status/scope/schedule/estimate/presentation/confirmationBasis/confirmedAt/occurredOn/withdrawn/version}与postLink{stage/action/original/excerpt}；state cursor/backlog/hot/failures/watermarks |
| 通知 | 扩现有targets/deliveries，承接 `delivery_leases` | target purpose/kind/configRef/enabledAt + content/event/call/version/dedupe→claim/sendstate/attempt/rawResponse/time/version；短期同题lease、同fact去重与unknown人工resolve；报告通知原本地实体不删 |
| 预算回执 | 扩现有ai/services/budget账本承接 `receipts/receipt_attempts/budgets/service_prices` | logicalInputKey/service/model/purpose/subject/prompt/config/attemptTag→attempt reservation、pending/received/completed/failed/unknown、rawResponse/requestID/usage/cost/error/timing/billedReview；rate与金额cap缺省阻断 |
| 运营设置/审计 | 复用现有operation/job证据，承接 `settings/audit_log/job_runs/stored_files` | actor/action/subject/reason/before/after→appendOnly audit；run start/finish/status/result/error；配置modelOverrides/targets/QR/flags/alerts/backup/indexnow状态与watermarks；files键/类型/尺寸/hash/保留与备份一致性 |
| 反馈 | 新 `feedback/feedback_bans` 等价实体 | text/email/pageURL/screenshot/sourceHash→id/status/note/forwardedAt/forwardError/version；ban/unban/erase/截图受控读取；原IP不存，删除联系材料可审计 |
| 后台准入 | 访问控制模式确认后 `admin_users/admin_sessions` 或现有本地安全边界等价承接 | password/OAuth/state/allowlist→principal/session/CSRF/expiry/UA绑定/credentialBindingHash/logout；用户“全量”与既定Demo模式由根任务统一定标，不在这里悄悄恢复产品用户体系 |

### 9.1 读取、报告与缓存复核后必须补正的验收

- 源参与模式/全文许可修改，上游是排 `publication.republish-source` 再重建投影；详情/OG的source mode有实时guard，但列表/RSS/全文投影并非后台提交即全完成。必须可见 queued/running/completed/failed，重启可恢复，限制收紧应新读优先采用live guard。
- 上游无全缓存主动purge：MCP items/daily30s；RSS fresh300+SWR900；固定周/月JSON fresh3600+SWR86400；站内报告index fresh60s/maxStale10min；文章/事件OG fresh3600+SWR600；报告OG默认浏览器86400/CDN604800+SWR86400。完整本地验收必须解决权限收紧/撤回的缓存失效，不能照搬长缓存后声称即时一致。
- 上游报告读取会保留网站不可用引用title，REST/MCP删其引用，但lead/overview/theme.summary没有重审，数据库缺失旧引用默认available。完整迁移需要修正缺失即未知/不可用及派生文字失效，避免旧主张外泄。
- `catchUpReports` default8只限制成功generated，不限制失败尝试；从最早已有本类刊开始，无刊时只补最新到期刊。持续失败时需另加尝试/时间预算，禁止一次扫无限历史。
- 本机收藏导出和30min列表后退快照可能保留旧title/summary；撤回收藏禁链接并标不可公开，不承诺浏览器已有副本消失。明确此本机边界和新读取一致性。
- IndexNow上游只发新增/更新public indexable，未按release gate筛，且不报撤回URL。完整SEO应补放行时间与删除通知合同；禁用仍零外发。


## 10. 全量目录、路由与任务覆盖清单（静态提取）
以下清单从固定源码文本提取，未导入或执行该项目。路由字符串只是上游行为索引；本地URL、owner/topic权限和唯一OpenAPI按HotKey合同定义。模板字符串保留占位，循环注册另列展开规则。
### 10.1 API路由
| 上游文件 | 方法与路径 |
|---|---|
| `apps/api/src/routes/admin-auth.ts` | `GET /api/auth/login`<br>`GET /api/auth/options`<br>`POST /api/auth/password`<br>`GET /api/auth/feishu`<br>`GET /api/auth/callback`<br>`GET /api/auth/check`<br>`POST /api/auth/logout`<br>`GET /api/admin/me` |
| `apps/api/src/routes/admin.ts` | `GET /api/admin/sources`<br>`POST /api/admin/sources`<br>`POST /api/admin/sources/preview`<br>`GET /api/admin/sources/:id`<br>`PATCH /api/admin/sources/:id`<br>`POST /api/admin/sources/:id/preview`<br>`POST /api/admin/sources/:id/fetch`<br>`GET /api/admin/content`<br>`GET /api/admin/content/:id`<br>`POST /api/admin/content/:id/visibility`<br>`POST /api/admin/content/:id/seo`<br>`POST /api/admin/content/:id/override`<br>`POST /api/admin/content/:id/rerun`<br>`POST /api/admin/content/:id/detach`<br>`POST /api/admin/stories/merge`<br>`GET /api/admin/feedback`<br>`PATCH /api/admin/feedback/:id`<br>`POST /api/admin/feedback/:id/erase`<br>`GET /api/admin/feedback/:id/screenshot`<br>`POST /api/admin/feedback-bans`<br>`DELETE /api/admin/feedback-bans/:hash`<br>`GET /api/admin/runs`<br>`POST /api/admin/receipts/:id/release`<br>`POST /api/admin/deliveries/:id/resolve`<br>`POST /api/admin/processing/requeue`<br>`GET /api/admin/monitor/events`<br>`GET /api/admin/monitor/posts`<br>`PATCH /api/admin/monitor/events/:id`<br>`POST /api/admin/monitor/events/:id/receipt-review`<br>`POST /api/admin/monitor/events/:id/withdrawn`<br>`POST /api/admin/monitor/relink`<br>`POST /api/admin/monitor/posts/:id/resolve`<br>`GET /api/admin/settings`<br>`POST /api/admin/settings/contact-qr`<br>`POST /api/admin/notify-targets/:key`<br>`PUT /api/admin/budgets/:service`<br>`GET /api/admin/models`<br>`POST /api/admin/models/:capability`<br>`GET /api/admin/selectbench`<br>`GET /api/admin/selectbench/:id`<br>`POST /api/admin/selectbench/import`<br>`GET /api/admin/nav-counts`<br>`GET /api/admin/audit` |
| `apps/api/src/routes/agent.ts` | `GET /api/v1/agent`<br>`GET /api/v1/agent/latest`<br>`GET /api/v1/agent/search`<br>`GET /api/v1/agent/hot`<br>`GET /api/v1/agent/stories/:publicId`<br>`GET /api/v1/agent/daily`<br>`GET /api/v1/agent/daily/:date`<br>`GET /api/v1/agent/codex-resets` |
| `apps/api/src/routes/feedback.ts` | `POST /api/site/feedback` |
| `apps/api/src/routes/feeds.ts` | `GET /feed.xml`<br>`GET /feed/full.xml`<br>`GET /feed/all.xml`<br>`GET /feed/daily.xml` |
| `apps/api/src/routes/ingest.ts` | `POST /api/ingest/items` |
| `apps/api/src/routes/leaderboard.ts` | `GET /api/site/leaderboard/boards/:key`<br>`GET /api/site/leaderboard/models/:slug`<br>`GET /api/site/leaderboard/sources`<br>`GET /api/site/leaderboard/sources/:key`<br>`GET /api/site/leaderboard/rules` |
| `apps/api/src/routes/mcp.ts` | `OPTIONS /api/mcp` |
| `apps/api/src/routes/media.ts` | `GET /api/img-proxy` |
| `apps/api/src/routes/og.ts` | `GET /og/site.png`<br>`GET /og/pages/:file`<br>`GET /og/items/:file`<br>`GET /og/posters/:file`<br>`GET /og/reports/:kind/:file`<br>`GET /og/topics/:file`<br>`GET /og/stories/:file` |
| `apps/api/src/routes/site.ts` | `GET /api/site/meta`<br>`GET /api/site/timeline`<br>`GET /api/site/pool`<br>`GET /api/site/items/:id`<br>`GET /api/site/items/:id/original`<br>`GET /api/site/stories/:publicId/followups`<br>`GET /api/site/groups/:factId/reports`<br>`GET /api/site/stories/:publicId/developments`<br>`GET /api/site/contact`<br>`GET /api/site/stats`<br>`GET /api/site/changelog`<br>`GET /api/site/items/availability`<br>`GET /api/site/topics`<br>`GET /api/site/topics/:slug`<br>`GET /api/site/hot`<br>`GET /api/site/stories/:publicId`<br>`GET /api/site/reports/:kind`<br>`GET /api/site/reports/:kind/latest-page`<br>`GET /api/site/reports/:kind/navigation/:key`<br>`GET /api/site/reports/daily/months/:month`<br>`GET /api/site/reports/:kind/:key`<br>`GET /items/:id/markdown`<br>`GET /api/site/codex-reset`<br>`GET /api/site/codex-reset/days/:date`<br>`GET /api/site/codex-reset/version` |
| `apps/api/src/routes/static.ts` | `GET /sitemap.xml`<br>`GET /llms.txt`<br>`GET /robots.txt`<br>`GET /.well-known/security.txt`<br>`GET /manifest.webmanifest`<br>`GET /openapi-v1.json`<br>`GET /${config.indexNowKey}.txt`<br>`GET /${icon}`<br>`GET /${dir}/:file`<br>`GET /contact/:file` |
| `apps/api/src/routes/v1.ts` | `GET /api/v1/items`<br>`GET /api/v1/hot-topics`<br>`GET /api/v1/stories/:publicId`<br>`GET /api/v1/dailies`<br>`GET /api/v1/dailies/latest`<br>`GET /api/v1/dailies/:date`<br>`GET /api/v1/${path}`<br>`GET /api/v1/${path}/latest`<br>`GET /api/v1/${path}/:key`<br>`GET /api/v1/selected/snapshot`<br>`GET /api/v1/selected/changes`<br>`GET /api/v1`<br>`GET /api/v1/*`<br>`GET /api/v1/codex-resets`<br>`GET /api/v1/codex-resets/recent` |

循环路由展开：周刊`/api/v1/weeklies`、`/latest`、`/:key`与月刊`/api/v1/monthlies`对应三个接口；RSS `/feed/category/:file`及`/feed/full/category/:file`；动态静态资源品牌/icons/provider/source/nameplate和IndexNow key路径；MCP由StreamableHTTP registerMcp登记`/api/mcp`的GET/POST/DELETE及OPTIONS，PUT/PATCH拒绝，不能只按app.get提取判断遗漏。`apps/api/src/app.ts`另有`GET /api/health`（DB探针、ms/release/no-store）、中央redirect/410/OAuth探测404、requestId与日志脱敏；均需接本地既有健康/错误/重定向机制。
### 10.2 Web路由文件（全部）
| 目录 | 文件 |
|---|---|
| `apps/web/app/routes` | `about.tsx`, `admin-login.tsx`, `agent.tsx`, `all.tsx`, `changelog.tsx`, `codex-reset.tsx`, `daily-archive.tsx`, `feedback.tsx`, `home.tsx`, `hot.tsx`, `item-original.tsx`, `item.tsx`, `leaderboard-boards.tsx`, `leaderboard-model.tsx`, `leaderboard-rules.tsx`, `leaderboard-source.tsx`, `leaderboard-sources.tsx`, `leaderboard.tsx`, `more.tsx`, `privacy.tsx`, `report-detail.tsx`, `report-latest.tsx`, `search-busy.tsx`, `starred.tsx`, `story.tsx`, `terms.tsx`, `topic.tsx`, `topics.tsx` |
| `apps/web/app/routes/admin` | `audit.tsx`, `content-item.tsx`, `content.tsx`, `feedback.tsx`, `index.tsx`, `layout.tsx`, `models.tsx`, `monitor.tsx`, `runs.tsx`, `selectbench-run.tsx`, `selectbench.tsx`, `settings.tsx`, `source-new.tsx`, `source.tsx`, `sources.tsx` |

### 10.3 业务handler与所有cron
业务队列：`content.analyze`、`content.extract-body`、`events.group`、`events.digest`、`sources.fetch`、`sources.fetch-x`、`sources.mp`、`notify.selected`、`publication.republish-source`、`media.prepare`；本地都接既有Job/Outbox/Kafka，禁止加入pg-boss事实源。
- `content.sweep`：上游`*/5 * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `content.translate`：上游`*/5 * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `hot.rank`：上游`*/5 * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `hot.snapshot`：上游`2 * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `stories.status`：上游`7 * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `stories.links`：上游`12 * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `reports.daily`：上游`0 8 * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `reports.weekly`：上游`0 10 * * 1`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `reports.monthly`：上游`30 10 1 * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `reports.catch-up`：上游`15 * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `ops.retention`：上游`30 3 * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `sources.icons`：上游`40 4 * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `seo.indexnow`：上游`50 5 * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `ops.recover`：上游`*/10 * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `ops.alerts`：上游`*/10 * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `ops.digest`：上游`0 9 * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `feedback.forward`：上游`*/10 * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `ops.backup`：上游`10 4 * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `reports.source-health`：上游`0 9 * * 1`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `leaderboard.round`：上游`5 2,8,14,20 * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `sources.schedule`：上游`* * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `sources.adapt-intervals`：上游`20 4 * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `sources.mp-reconcile`：上游`*/15 * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `monitor.tick`：上游`* * * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。
- `monitor.lookback`：上游`40 4 * * *`（Asia/Shanghai），功能/开关/补运行语义见矩阵。

### 10.4 Backend全部目录责任映射
| 目录 | 固定源码文件 | 本报告验收族 |
|---|---|---|
| `admin/` | `auth.ts`, `content.ts`, `feedback.ts`, `models.ts`, `monitor.ts`, `navigation.ts`, `runs.ts`, `selectbench.ts`, `settings.ts`, `sources.ts` | AD/FB/AI/SC/CX |
| `content/` | `extract.ts`, `markdown.ts`, `materials.ts`, `sanitize.ts` | MA |
| `editorial/` | `analyze.ts`, `input.ts`, `models.ts`, `prompts.ts`, `translate.ts`, `vocabulary.ts`, `writing.ts` | AI/EV |
| `events/` | `consolidate.ts`, `corrections.ts`, `derived-content.ts`, `digest.ts`, `group.ts`, `hot.ts`, `merge.ts`, `recall.ts`, `relate.ts` | EV/HE |
| `ingest/` | `items.ts` | SC07 |
| `jobs/` | `content.ts`, `events.ts`, `notify.ts`, `publication.ts`, `queue.ts`, `sources.ts` | OP01及所有业务族 |
| `leaderboard/` | `access.ts`, `directory.ts`, `fetch/configuration.ts`, `fetch/csv.ts`, `fetch/github.ts`, `fetch/hf.ts`, `fetch/identity.ts`, `fetch/index.ts`, `fetch/rank.ts`, `fetch/refresh.ts`, `fetch/sources/arena.ts`, `fetch/sources/artificial-analysis.ts`, `fetch/sources/deepswe.ts`, `fetch/sources/epoch.ts`, `fetch/sources/eqbench.ts`, `fetch/sources/livebench.ts`, `fetch/sources/mercor.ts`, `fetch/sources/taptap.ts`, `fetch/sources/terminal-bench.ts`, `fetch/sources/vals.ts`, `fetch/store.ts`, `fetch/types.ts`, `fetch/unzip.ts`, `method/compute-worker.ts`, `method/compute.ts`, `method/inputs.ts`, `method/kemeny.ts`, `method/ndtr.ts`, `method/run.ts`, `method/v15.ts`, `model-weights.json`, `prices.ts`, `read.ts`, `registry.ts`, `source-registry.json` | LB |
| `lib/` | `cache.ts`, `cursor.ts`, `http-fetch.ts`, `ids.ts`, `image-url.ts`, `shutdown.ts`, `text.ts`, `url.ts` | OP/PU/SC/ME，公共安全/缓存/游标/ID/文本/URL/停止语义 |
| `media/` | `images.ts`, `imgproxy.ts`, `prepare.ts`, `renditions.ts` | ME01/SEO02 |
| `monitor/` | `assemble.ts`, `read.ts`, `recognize.ts`, `scan.ts`, `time.ts` | CX |
| `notify/` | `deliver.ts`, `feishu.ts`, `selected-content.ts`, `selected.ts` | NT/CX/OP/FB |
| `operations/` | `alerts.ts`, `backup.ts`, `feedback.ts`, `heartbeat.ts`, `indexnow.ts`, `recover.ts`, `reports.ts`, `retention.ts`, `watch.ts` | OP/SEO/FB |
| `providers/` | `dajiala.ts`, `embeddings.ts`, `jina.ts`, `llm.ts`, `receipts.ts`, `socialdata.ts` | AI/SC/OP02 |
| `publication/` | `agent.ts`, `availability.ts`, `detail.ts`, `feeds.ts`, `followups.ts`, `groups.ts`, `hot.ts`, `items.ts`, `links.ts`, `llms.ts`, `monitor.ts`, `og.ts`, `pool.ts`, `publish.ts`, `reports.ts`, `rules.ts`, `scope.ts`, `sitemap.ts`, `stories.ts`, `timeline.ts`, `topics.ts`, `v1.ts` | PU/RE/RP/OUT/SEO/CX |
| `reports/` | `compose.ts` | RP |
| `site/` | `contact.ts`, `meta.ts`, `stats.ts` | SEO/OP06/AD04 |
| `sources/` | `collect.ts`, `config-keys.ts`, `icons.ts`, `json-list.ts`, `mp.ts`, `rss.ts`, `types.ts`, `web-list.ts`, `x.ts` | SC/OP06 |
| backend顶层 | `audit.ts/config.ts/db.ts` | AD/OP/全部实体；沿用本地数据库/配置/审计，不复制全局SQL客户端 |

### 10.5 数据与构建资产
`packages/contracts/src/`仅作DTO/校验语义参考，本地由Pydantic→FastAPI运行OpenAPI→生成客户端；不复制第二合同生成链。`database/migrations/`用于识别上述实体和约束，不直接应用；`database/seeds/`模型名录/官方价格可当有出处的固定资产迁用。`industry/`全套prompts/taxonomy/topics/source示例/selection/site/features/pages/changelog需要保留功能但换本地行业配置和品牌；`industry/brand`名称Logo不获MIT授权。`assets/og-fonts`遵OFL，model-providers与leaderboard-source标识遵独立NOTICE。`scripts/`导入/评测/重聚/采集/榜单/运维脚本行为全部由本地CLI或后台适配，不执行原Node脚本。`docs/`是上游参考与截图，不是部署和真实验收证据。
