# Ripplesight BACKLOG

需求、设计与计划的唯一规格入口为[00～58编号目录](docs/index.md)。本文只记录当前差距、执行次序和证据；产品要求以FR/BR/NFR/AC为准，代码和既有表结构不决定需求正确性。

## 核对基线与结论

2026-10-12以已推送main的`569ea67c`静态核对核心实现；该提交包含本轮规格重建，之前的任务累计/执行轮计量提交也已随main推送。本次后续修改仅重排BACKLOG，没有改业务代码、schema或迁移，没有连接业务库、启动服务或调用真实平台/模型/通知。

**核心闭环尚未完成。** 已有准入、原生身份/版本、查询回执、部分增量计量、逐评论分析、事件修订、采集暂停围栏、预算连续扣账和unknown发送保护；仍有确定行为冲突及未实现的业务合同。下文“已有”只表示代码路径存在，“差距”有源码依据，“待核对”尚不能证明全路径，“待验收”需要独立环境/真实来源/自然时间/本人接收。既有测试入口未在本轮重跑，不能据此更新通过状态。

规格重建已补原始意图、功能/非功能需求、AC、用户故事及数据库字段/关系/事务；59组文件名/H1、185份Markdown链接/锚点和10项文档工具回归通过，原始需求、数据库及文档三路只读审查无剩余文档阻断。这仅证明文档一致性，目标设计仍须评审，不能视作DDL已实施或产品能力通过。

本次实现对照另由采集链、持续运行/通知、分析/事件三路独立只读复核；已修正国内POC排期冲突、身份键泛化及评测/排序措辞，最终无剩余BACKLOG审查阻断。文档链接检查、10项文档工具回归和差异空白检查通过；这些不增加业务验收通过项。

## 决策与实施边界

- [ ] **GOV-00-01～03 / VR-11-01**：评审原始意图登记、FR/BR、18类NFR及AC；补充尚未找回的原始要求。核心优先，其余保留重审。数据库逐实体选择复用、改造或替换，先证明约束再决定表名，不按“55张候选表”机械建表。
- [ ] **FR-08-03**：冻结国内主流平台POC清单及逐平台能力/免费准入依据。单个B站切片不能代表国内主流覆盖；HN仅作合同对照，不能替代国内POC。X/Instagram等目标保留，费用不明、权限未准入或风控时不得请求。
- [ ] **FR-05-03 / FR-07-02/04/05 / VR-11-01**：用分层基线冻结热点、重要性、增长及排序规则，确定三类提醒交付批次；首次热点可以是最小切片，重要事实/更正与可比增长仍属于核心，不能自动降为辅助P1。尚未确认的阈值不得自行编造。
- [ ] **NFR / VR-11**：冻结真实负载、质量、时效、容量、保留/清理、RPO/RTO及测量环境。正式阈值依赖基线，合同和固定样本准备可先做；真实请求与业务库升级遵守AGENTS的独立授权边界。

这些决策不阻塞已确定错误的修正方案与受控反例准备。每个实施切片须更新对应设计/计划、验证影响范围、独立只读审查，再回填本文件；本清单不创建自动定时开发或额外真实请求授权。

## P0核心执行队列

所有项目当前均未关闭。表中FR/VR逐项对应同编号AC，关闭时分别回填证据。顺序按业务依赖排列；CORE-01保护、CORE-00准入准备和CORE-11评测准备贯穿全程，不能等最后才处理。

| 次序与任务 | 对应要求 | 依赖及具体交付物 | 关闭条件 |
|---|---|---|---|
| CORE-00 准入与评测准备 | 00、08、11 | 国内POC能力清单、零费用/权限依据；分层校准/保留样本方案及基线工具 | 能说明每个平台可回答的问题、限制和停止条件；待确认决策显式登记 |
| CORE-01 隔离、身份与恢复保护 | FR-10-01～03、FR-29-01 | 全读取/派生/导出权限路径清单；身份验证失败恢复；独立删除/撤权重放与恢复隔离方案 | 跨owner与旧修订/媒体/导出反例通过；旧备份在重放前不可暴露；挑战不可重用且提交失败可解释恢复 |
| CORE-02 草稿与确定查询语义 | FR-01-01～03、FR-02-01 | 拆开保存草稿、启用准入和执行；统一预览/执行匹配与未知语言状态 | 来源未就绪仍可存有效草稿；启用/执行明确拒绝；编辑冻结、语义与待判断语言AC通过 |
| CORE-03 身份、比较基线与执行计量 | FR-03-01～03、FR-46-01/02 | 父ID迟到关系补齐；可靠首次身份/比较基线；执行轮、任务累计和预算周期口径及字段映射 | 重复/编辑/互动/未知互斥；删历史不把旧身份变新增；父关系补齐不造身份；无归属证据保留未知 |
| CORE-04 旧帖讨论显式跟踪 | FR-02-02～04 | 跟踪纳入/退出/到期、频率/上限和版本；原帖窗口外评论刷新及回执 | 旧帖新评论可发现；退出/到期后阻止新刷新；根评论/回复/缺父和截断分别解释 |
| CORE-05 独立相关性与阅读排序 | FR-04-01、FR-09-01～04、FR-36-01 | 各分析维度独立状态；保留评论冻结输入；相关性/相似度/新鲜度排序合同及用户解释 | 非法情感/观点不作废有效相关性；不足/未知可辨；标注的新旧/相关样本排序可复核，游标稳定 |
| CORE-06 具体事件、说法与修订 | FR-04-02/03、FR-05-01/02、FR-38-01、FR-39-01/02 | 候选消费与归并理由；说法/支持/确认/反证/撤回及主体时间依据；规范事件合并/拆分继承 | 单材料线索不冒充证实；重复报道不增加事实；更正引用真实修订；纠错CAS、历史权限与继承AC通过 |
| CORE-07 自然窗口、作用域与预算 | FR-06-01～03、FR-47-01、FR-50-01核心部分、46预算合同 | 不可变调度生效区间/锚点/启停历史；独立采集/分析/发送授权；预算停用与版本历史；核心模型停用及用量未知合同 | 离线跨改频/删来源仍复算完整应执行分母；暂停恢复不复活旧采集；关闭预算作用域禁止新请求，改版不清额度；停用后新分析延后/拒绝、在途旧版策略明确，未知token与已知成本小计可辨 |
| CORE-08 可比24小时趋势与热点 | FR-05-03、FR-07-01/05 | 唯一相关原帖、作者、新事实与独立互动指标；覆盖/规则/来源/时间窗可比标记 | 缺基线/断采/补采/来源变化给抑制或不可比；阈值版本和分母可追溯，未知不补零 |
| CORE-09 目标验证与通知静默 | FR-35-01/03、FR-07-03 | 本人显式验证具体地址版本、摘要/有效期；启停管理、换址重验；静默/not-before合同 | provider accepted不作地址验证；换址失效；静默只影响发送作用域；失效目标在外发前阻断 |
| CORE-10 关注、三类提醒与语义去重 | FR-07-02～05、FR-35-02/04 | 规范事件及事实进展去重；关注/取消与合并继承；首次热点、重要事实/更正、可比增长及可读抑制原因；已读独立 | 跨规则/目标/渠道版本不重发首次；同一事实进展一次；取消阻止未外发；合并不复活已取消关注；unknown先核对 |
| CORE-11 独立评测与真实闭环验收 | VR-11-01～03及全部核心AC | 先补受控反例，再做真实两轮、独立质量评测、完整消费链后的七个连续自然日及本人接收证据 | 全窗口分母可核查；两轮自然成功及事件更新；自然达标提醒本人收到；硬门槛无失败，页面同步验收 |

依赖主线：CORE-00/01 → CORE-02/03/04 → CORE-05/06 → CORE-07/08/09 → CORE-10 → CORE-11正式观察。调度/目标验证和评测工具可提前并行准备；不得以单一来源、测试通过或手动发送替代完整闭环。

## 源码依据与差距

### CORE-01：访问、身份和恢复

- **已有**：服务端会话owner与CSRF/运营边界在[dependencies.py](backend/app/api/dependencies.py#L527)；当前资源删除屏障在[evidence/services.py](backend/app/evidence/services.py#L161)，精确观察依赖清理覆盖报告/告警/公开/事件/分析在[lifecycle.py](backend/app/content/lifecycle.py#L114)。不能重列为完全缺失；仍须逐读路径核对标题、计数、媒体、固定修订及导出是否执行当前许可。
- **确定差距**：恢复验证只执行隔离dump/restore、表数量与读写核对及对象校验，[restore.py](backend/app/backups/restore.py#L132)未接入备份后删除/撤权重放。当前删除指令与资源同库且FK级联，[models.py](backend/app/evidence/models.py#L236)不能独自提供跨旧备份的独立屏障。补独立最小账本、恢复隔离及重放完成判据；不把现有恢复工具当作安全上线恢复已完成，也不声称当前临时恢复库已对外暴露。
- **已有及目标差距**：Redis脚本原子一次消费、尝试限制/重发失效已有，[verification_store.py](backend/app/identity/adapters/verification_store.py#L56)；账户与首会话在同一PG事务且邮箱/GitHub有唯一约束，[services.py](backend/app/identity/services.py#L340)。但[邮件消费](backend/app/identity/services.py#L238)先于PG事务，消费后建号/会话提交失败没有跨存储恢复收据，未满足29目标事务合同。应评审同事务或等价可恢复方案，不误报验证码可重放；不因身份存储内嵌而机械新建表。

### CORE-02～04：配置、采集和计量

- **已有**：关键词规范化、三组词、规则版本、手动/定时查询受理/跳过和冻结配置，[query_plans.py](backend/app/jobs/query_plans.py)、[runs.py](backend/app/monitors/runs.py)。来源目录及受控样本不是免费准入或真实覆盖证明。
- **确定差距**：创建/更新主题先要求来源已应用且就绪，[services.py](backend/app/monitors/services.py#L868)、[来源检查](backend/app/monitors/services.py#L1398)，与FR-01-01有效草稿可保存冲突。当前[跨组校验](backend/app/monitors/services.py#L405)还拒绝any/all同词及任意正向词与exclude重合，超过目标中all/exclude直接矛盾的范围，例如any=[Alpha,Beta]、exclude=[Alpha]仍可匹配Beta。未知语言在[discovery.py](backend/app/content/discovery.py#L499)按filtered丢弃，不能表达待判断，[来源说明](backend/app/connections/search_contracts.py#L49)也须同步修正。
- **提案分歧待样本冻结**：当前[匹配函数](backend/app/monitors/services.py#L418)对CJK包含、Latin词边界，预览与执行共用，不能说二者已不一致。01中的规范化字串包含是待样本评审提案；用真实词组样本冻结匹配版本后同步预览、执行和说明，不为兼容旧代码保留错误方案，也不冒充用户已批准新算法。
- **已有及确定差距**：当前原生身份键为owner/source_key/object_type/native_scope/external_id，[models.py](backend/app/content/models.py#L31)，内容版本、观察和发现已分开。[Threads强原生映射](backend/app/sources/editorial_identity.py#L25)另有证据合同，不能泛化为所有平台跨连接映射已完成。已知父ID但正文缺失的placeholder能补齐；父ID从None迟到则在[services.py](backend/app/content/services.py#L925)先认作root、[后续关系检查](backend/app/content/services.py#L1030)报冲突，未满足AC-03-01身份不变而补关系。
- **已有及确定差距**：任务累计、互斥四类和lease_epoch执行轮差分已实现，[任务执行读取](backend/app/jobs/services.py#L3235)；但[分类](backend/app/content/collection_counts.py#L65)把“无保留前观察”直接计new，[历史查询](backend/app/content/services.py#L723)仅基于当前保留观察，历史清理会让旧对象误报新增。补可靠首次身份及比较证据；证据过期应unknown，旧dedup字段或旧口径不得作为兼容理由保留错误分类。
- **确定差距**：自动评论扫描按本地建档年龄、近期观察和互动限额选候选，[services.py](backend/app/content/services.py#L2910)、[候选读取](backend/app/content/services.py#L2981)，尚无用户显式持久跟踪集合及纳入/退出/到期合同；不是仅扩大搜索窗口即可补齐。根评论/回复页上限和平台真实能力须逐项验收，不宣称全量。
- **准入与能力差距**：逐请求取消/连接版本/准入核对已有，[discovery.py](backend/app/content/discovery.py#L125)。但[执行能力](backend/app/sources/contracts.py#L14)和[研究矩阵](backend/app/connections/catalog_schemas.py#L16)缺独立详情/删除同步等完整维度，[目录](backend/app/connections/catalog.py#L49)仍以HN required、B站candidate标记旧排期。更新为国内POC并逐能力显示支持/不支持/未知及证据日期；[B站适配器](backend/app/sources/adapters/bilibili_chrome.py#L193)目前仅首页根评论、不遍历回复，不能用HN父链代替国内讨论验收。
- **待核对**：普通feed更换目标时的来源实例命名空间/映射；活跃执行的上游返回与保留观察快照时间、超过当前详情窗口的执行历史可达性。现有轮次归属与历史未知字段已有，不能按候选表名不同重列为无执行轮。

### CORE-05～06：分析、事件和事实

- **已有及确定差距**：v2允许情感为空，已采评论有独立相关性、不足/未知/延后及冻结原帖/父链；但帖子[AnnotationOutputItem](backend/app/analysis/schemas.py#L301)仍强制bool并同对象校验情感/观点，[解析](backend/app/analysis/services.py#L644)会因非法其他维度使整对象失效。[读取](backend/app/analysis/schemas.py#L50)仅单一result_state。已有null容忍切片不能等同FR-04-01/09-01各维独立状态、引用及版本完成。
- **已有及确定差距**：候选冻结输入、单材料路径和修订冲突检查已有；[EventDecision](backend/app/events/schemas.py#L106)仅same_event布尔，缺不足暂缓及支持/反对理由；[用户状态](backend/app/events/schemas.py#L139)只有active/merged，没有候选读取消费。成员数量线索提示不能替代候选解释。
- **确定差距**：资料已在服务端本人可读集合检索，未仅搜索当前页；但[列表排序](backend/app/content/services.py#L1553)按UUID，[事件读取](backend/app/events/reads.py#L191)按first_seen过滤/倒序，旧事件今日更新不能表达最近变化。补跨页相关性/新鲜度排序、采用时间字段及稳定游标，区分相似度、相关性和热度并公开组合排序依据。
- **已有及确定差距**：稳定事实身份、材料版本、自动归并delta及CAS纠错已有，[fact_delta.py](backend/app/events/fact_delta.py#L95)、[corrections.py](backend/app/events/corrections.py#L36)。但[事实状态](backend/app/events/fact_models.py#L45)只有confirmed/unreviewed/merged，[写入](backend/app/events/fact_writer.py#L273)按归组关系置confirmed，不能表示来源声称/确认/争议/反证/撤回。旧事件修订仍[读取当前事实内容](backend/app/events/facts.py#L400)，纠错[before/after](backend/app/events/corrections.py#L500)不冻结事实内容状态。补不可变事实修订和支持/反证关系；自动归并差分不等于人工纠错/24小时变化或事实真伪确认。
- **继承差距**：纠错已保留actor/reason、成员退出修订及合并指向；仍需影响预览、关注迁移与提醒前身历史并集/拆分继承，见CORE-10。不得用新event_id重新取得首次提醒资格。

### CORE-11及50：评测与模型资源

- **已有及确定差距**：精选评测有gold指纹、seed、分层抽样及模型/提示冻结，[evaluation_services.py](backend/app/analysis/evaluation_services.py#L147)；[事件关系评测](backend/app/analysis/evaluation_relations.py#L82)有四类混淆矩阵、阈值扫描及同样本版本比较，不能写成没有事件评测。但[run合同](backend/app/analysis/evaluation_models.py#L20)只有任意split标签，缺校准/保留角色、校准与保留集之间的重叠/污染保护及预先冻结正式阈值；冻结保留集的合法跨版本对照不受禁止。补关键词真实相关性、误/漏合并、新事实/反证和排序套件；源码相似度/时间窗/置信参数不作已校准门槛。
- **已有及确定差距**：模型路由配置CAS、审计和新任务冻结已有，[capability_services.py](backend/app/ai/capability_services.py#L140)；但[切换输入](backend/app/ai/capability_schemas.py#L270)的null表示恢复默认，非逐能力停用。Codex未报告token时[适配器](backend/app/ai/adapters/codex_app_server.py#L324)给0及usage_reported=False，[调用持久化](backend/app/ai/services.py#L647)未保留该标记，聚合无法区分未知和真实0；[成本聚合](backend/app/ai/capability_services.py#L288)缺未知覆盖。真实用量未知表达及停用保护影响核心时按P0处理，扩展展示按P1评审，不能将已知小计当总消费。

### CORE-07：持续监测和预算

- **已有**：调度漏轮回执及最新受理推进同事务，[scheduler.py](backend/app/worker/scheduler.py#L550)；采集任务状态序号围栏在[collection_topics.py](backend/app/jobs/collection_topics.py#L32)，领取/请求/重试复核，暂停后恢复不复活旧任务。
- **确定差距**：当前只领取enabled调度，[services.py](backend/app/monitors/services.py#L498)；移除来源删调度，[删除](backend/app/monitors/services.py#L1473)；改频原地改interval/next_due，[更新](backend/app/monitors/services.py#L1506)。已有due账本不能还原缺少历史政策的完整离线分母。告警仍按topic active过滤，[alert_services.py](backend/app/notifications/alert_services.py#L434)，采集暂停会一并阻断通知，必须拆开作用域授权。
- **已有**：改预算限额递增版本，[services.py](backend/app/jobs/services.py#L1377)；固定窗口按稳定policy ID，[窗口](backend/app/jobs/services.py#L1847)；已用/预留计入余额，[扣账](backend/app/jobs/services.py#L1551)。没有证据证明改版会清额度，不推翻已有保护。
- **目标差距待反例验证**：预算选择仅含enabled政策，[services.py](backend/app/jobs/services.py#L1815)，准入只强制global存在；关闭source层可能退回global而不阻止该作用域请求。按46目标停用语义补反例及政策生效历史复算；停用不得清理已用/预留，未知消费保守占用。

### CORE-08～10：趋势、提醒和关注

- **已有及差距**：[alert_reading.py](backend/app/events/alert_reading.py#L177)已有同公式/来源集合基线与权限核对；[heat_schemas.py](backend/app/events/heat_schemas.py#L12)的48小时参与度不是FR-07-01真实24小时唯一原帖/作者/新事实及独立互动统计。补完整分母、最低样本、迟到/补采与不可比抑制。
- **确定差距**：[alert_schemas.py](backend/app/notifications/alert_schemas.py#L10)只有negative_count/heat_increment；[alert_services.py](backend/app/notifications/alert_services.py#L577)按evaluation.id去重，冷却后新评估可以重发。尚未实现三类核心触发及owner+规范事件/进展的跨版本业务去重；规则版本不可重置首次历史，合并前身也须继承。
- **已有及差距**：目标revision检查、CAS及外发前失效阻断已有；[alert_services.py](backend/app/notifications/alert_services.py#L49)将同revision一次provider accepted历史作verified，缺具体地址挑战、摘要及有效期；[TargetInput](backend/app/notifications/schemas.py#L45)缺通知静默/not-before管理。现有运营测试发送不等于本人已验证地址。
- **确定差距**：现有可选event_id只限定规则范围，未发现显式事件关注/取消、关注起点/版本、合并survivor继承及公开固定发布修订投影合同。关注不能用收藏/已读或规则event筛选替代；公开关注读取用户owner与事件owner必须分开，不能扩大到私有原始证据。已读写合同亦待补，不能改变去重/发送历史。
- **已有及验收差距**：[executor.py](backend/app/notifications/executor.py#L169)中断sending转unknown，已记录accepted后恢复不再外发；[operator.py](backend/app/notifications/operator.py#L50)支持带CAS/审计人工核对。保留unknown先核对保护；succeeded目前表示提供方接受，不能记录为本人已收到或实际送达。

## 数据库实施前门槛

- [ ] 建立目标责任→现有表/约束/消费者映射，优先CORE-01/03/04/06/07/09/10；现有content_native_identities、content_versions、content_observations、job_attempts、预算窗口等已有对应责任，不据表名差异认定缺失。
- [ ] 对确定差距先验证唯一键、owner复合FK、版本有效区间、规范事件谱系、原子操作/Outbox、unknown结算及删除影响；身份补关系和历史清理增量反例必须在独立库验证。
- [ ] 给出空库结构与既有数据迁移、重复/非法引用处理、索引查询基线、回滚和恢复重放方案；无法证明旧数据的状态保留unknown，不编造首次/确认/已送达。
- [ ] 冻结迁移方案并通过独立审查后再实施DDL；业务库升级单独授权。辅助实体先验证价值再定物理表，禁止为对齐文档批量建表或保留错误兼容分支。

## 12–58 保留能力与入口复核清单

以下保留上次页面扫描取得的入口和待办，本轮没有重新验收全部辅助页面；“已有入口”不等于符合新FR/AC。涉及核心闭环的29、32～39、44、46～50由上方CORE任务覆盖，其余按价值重评后排期。分页条数、组件复用和现有上限只描述当前实现，不约束目标方案。日/周报告、模板降级、验证订阅/退订、单向Obsidian导出及引文问答的历史意图均保留；引文问答先评审价值、许可及隐私，不据此解冻在线项目文档系统。动态页面正式验收须覆盖桌面/390px正常、空、加载、错误、无权限及键盘状态。

### 公开阅读与模型榜

| 编号及文档 | 已有入口（此前源码扫描） | 待补齐 / 待核对 | 待验收 |
|---|---|---|---|
| [12 今日热点](docs/requirement/12-今日热点.md) · [设计](docs/design/12-今日热点.md) · [计划](docs/plan/12-今日热点.md) | 分类URL、资讯分批展开、上升事件与最新公开日报分别读取，空/错状态保留。 [home-content.tsx](frontend/src/app/components/home-content.tsx#L39) | 四项站点业务统计为“—”，负面区块缺数据；现有site stats不等于所需事件/24h/负面指标。RSS入口与冻结边界对齐。 | 真实零值/未知、热点排序及许可变更；24h依赖07。 |
| [13 探索资讯](docs/requirement/13-探索资讯.md) · [设计](docs/design/13-探索资讯.md) · [计划](docs/plan/13-探索资讯.md) | 公开资讯q/来源筛选、游标与时间线读取；URL变化清游标，搜索可预填新主题。 [page.tsx](frontend/src/app/discover/page.tsx#L33) | 事件/评论检索与情感筛选尚无完整入口；现有搜索只覆盖资讯，禁用项不能算完成。 | 字面AND、来源联动、游标边界及当前许可。 |
| [14 公开专题目录](docs/requirement/14-公开专题目录.md) · [设计](docs/design/14-公开专题目录.md) · [计划](docs/plan/14-公开专题目录.md) | 公司/领域/类型目录、配置专题与真实可读计数。 [page.tsx](frontend/src/app/discover/topics/page.tsx#L15) | 新FR/AC全项复核待办；公开计数/许可完整性待核对。 | 真实空目录、近期窗口与无许可不计数。 |
| [15 公开专题详情](docs/requirement/15-公开专题详情.md) · [设计](docs/design/15-公开专题详情.md) · [计划](docs/plan/15-公开专题详情.md) | 专题定义、总量/近期量、20条分页与关联导航；不存在独立404。 [page.tsx](frontend/src/app/discover/topics/[slug]/page.tsx#L20) | 新FR/AC全项复核待办。 | 动态slug、分页末尾、错误与撤许可。 |
| [16 公开事件目录](docs/requirement/16-公开事件目录.md) · [设计](docs/design/16-公开事件目录.md) · [计划](docs/plan/16-公开事件目录.md) | 独立公开热事件目录，当前接口最多20条，不伪造分页。 [page.tsx](frontend/src/app/discover/stories/page.tsx#L10) | 事件资格、候选解释和窗口统计依赖04/07。 | 真实排序、零结果及许可收紧。 |
| [17 公开事件详情](docs/requirement/17-公开事件详情.md) · [设计](docs/design/17-公开事件详情.md) · [计划](docs/plan/17-公开事件详情.md) | 事件摘要、可读来源/报道、固定revision与7日发展读取，分享链接可用。 [public-story-reading.tsx](frontend/src/app/discover/stories/[eventId]/components/public-story-reading.tsx#L35) | 关注/收藏按钮禁用；情感/观点、24h历史和本轮事实差分未完整提供。 | 公开许可与无权/不存在、证据可达、时间线去重。 |
| [18 公开资讯阅读](docs/requirement/18-公开资讯阅读.md) · [设计](docs/design/18-公开资讯阅读.md) · [计划](docs/plan/18-公开资讯阅读.md) | 正文/元数据/来源外链、媒体、本机收藏已读与阅读位置恢复。 [item-reader.tsx](frontend/src/app/items/[contentId]/components/item-reader.tsx#L42) | 新FR/AC全项复核待办；媒体及许可全路径仍待核对。 | 真实正文降级、失效媒体、阅读恢复、键盘与清洗。 |
| [19 收藏与阅读记录](docs/requirement/19-收藏与阅读记录.md) · [设计](docs/design/19-收藏与阅读记录.md) · [计划](docs/plan/19-收藏与阅读记录.md) | 本机资讯收藏、已读、搜索、笔记、批量操作、JSON导入导出与Markdown导出已有实现。 [local-reading.tsx](frontend/src/components/publication/local-reading.tsx#L67) | 事件/评论/刊期等多类型收藏与关注尚不可用；不要重复立项已有JSON迁移。 | 500收藏/5000已读上限、2000字笔记、导入冲突、批量删除及导出不带受限全文。 |
| [20 最新公开刊物与个人报告详情](docs/requirement/20-最新公开刊物与个人报告详情.md) · [设计](docs/design/20-最新公开刊物与个人报告详情.md) · [计划](docs/plan/20-最新公开刊物与个人报告详情.md) | 最新公开刊物与UUID个人报告分流、目录/导航独立失败、个人报告详情导出入口。 [page.tsx](frontend/src/app/reports/[reportId]/page.tsx#L21) | 新FR/AC全项复核待办；报告生成和真实投递未验收。 | 固定版本/owner、最新刊缺失、导出与材料撤回。 |
| [21 公开固定刊期阅读](docs/requirement/21-公开固定刊期阅读.md) · [设计](docs/design/21-公开固定刊期阅读.md) · [计划](docs/plan/21-公开固定刊期阅读.md) | 固定刊期读取、正文/亮点/事件事实与打印入口；不存在不回退最新刊。 [public-edition-reader.tsx](frontend/src/app/reports/[reportId]/[key]/components/public-edition-reader.tsx#L37) | 社交槽位、评论/情感分区数据仍不完整；不能按空壳宣称已产出。 | 固定key、修订一致、分区真实空/错及打印可读。 |
| [22 公开刊物归档](docs/requirement/22-公开刊物归档.md) · [设计](docs/design/22-公开刊物归档.md) · [计划](docs/plan/22-公开刊物归档.md) | 公开归档20条和before_key，日刊日历初始取最新条目的月份，空目录按上海时区当前月。 [page.tsx](frontend/src/app/reports/[reportId]/archive/page.tsx#L19) | 新FR/AC全项复核待办。 | 历史刊翻页、跨时区日历和空月份。 |
| [23 模型综合榜](docs/requirement/23-模型综合榜.md) · [设计](docs/design/23-模型综合榜.md) · [计划](docs/plan/23-模型综合榜.md) | 固定发布run、0–100得分、开放权重证据、发布缺失与服务错误区分。 [board-reading.tsx](frontend/src/components/leaderboard/board-reading.tsx#L24) | 名次变化为“—”，周历史未提供，长上下文筛选禁用；保留缺口待评审。 | 真实发布run、证据/价格快照、未知值和筛选一致性。 |
| [24 模型分项榜](docs/requirement/24-模型分项榜.md) · [设计](docs/design/24-模型分项榜.md) · [计划](docs/plan/24-模型分项榜.md) | 分项参数校验与同一BoardReading/发布run复用。 [page.tsx](frontend/src/app/leaderboard/category/[board]/page.tsx#L12) | 依赖23的历史与筛选缺口，不另造一套数据。 | 动态board、404/503、排序与综合榜口径一致。 |
| [25 模型详情](docs/requirement/25-模型详情.md) · [设计](docs/design/25-模型详情.md) · [计划](docs/plan/25-模型详情.md) | 模型分项、来源证据、比较组及带来源/币种/验证日期的价格。 [model-reading.tsx](frontend/src/app/leaderboard/models/[slug]/components/model-reading.tsx#L38) | 新FR/AC全项复核待办；数据完整性与实际依赖可用性未验收。 | 动态slug、缺项/未知价格、快照与汇率日期。 |
| [26 评测来源目录](docs/requirement/26-评测来源目录.md) · [设计](docs/design/26-评测来源目录.md) · [计划](docs/plan/26-评测来源目录.md) | 评测来源目录、来源状态、预算和run相关信息。 [sources-reading.tsx](frontend/src/app/leaderboard/sources/components/sources-reading.tsx#L16) | 新FR/AC全项复核待办；展示目录不证明已完成真实抓取。 | 发布缺失、失败来源与局部读取失败。 |
| [27 评测来源详情](docs/requirement/27-评测来源详情.md) · [设计](docs/design/27-评测来源详情.md) · [计划](docs/plan/27-评测来源详情.md) | 来源详情、原始快照、别名与排除解释。 [source-reading.tsx](frontend/src/app/leaderboard/sources/[sourceKey]/components/source-reading.tsx#L23) | 新FR/AC全项复核待办。 | 动态sourceKey、快照追溯、许可与错误分支。 |
| [28 模型榜计算规则](docs/requirement/28-模型榜计算规则.md) · [设计](docs/design/28-模型榜计算规则.md) · [计划](docs/plan/28-模型榜计算规则.md) | 只读计算规则与发布run配置/常量展示。 [rules-reading.tsx](frontend/src/app/leaderboard/rules/components/rules-reading.tsx#L24) | 新FR/AC全项复核待办；不能把规则展示等同重算正确。 | 独立数据重算、最低样本/缺失项及版本一致性。 |

### 账户与个人监测工作区

| 编号及文档 | 已有入口（此前源码扫描） | 待补齐 / 待核对 | 待验收 |
|---|---|---|---|
| [29 登录与验证注册](docs/requirement/29-登录与验证注册.md) · [设计](docs/design/29-登录与验证注册.md) · [计划](docs/plan/29-登录与验证注册.md) | 首页背景登录弹窗、密码/邮件/GitHub路径、安全returnTo和会话错误状态。 [page.tsx](frontend/src/app/login/page.tsx#L14) | 身份一次消费与建号/会话跨存储失败恢复见CORE-01；既有键盘修复保留，真实邮件/OAuth与动态重排仍待验收。 | 真实身份流程、过期验证码与会话撤销；受控键盘不代替真实登录验收。 |
| [30 账户与订阅设置](docs/requirement/30-账户与订阅设置.md) · [设计](docs/design/30-账户与订阅设置.md) · [计划](docs/plan/30-账户与订阅设置.md) | 个人资料/头像读写、凭据、身份连接和报告邮件订阅入口。 [account-settings.tsx](frontend/src/app/account/components/account-settings.tsx#L55) | 新FR/AC全项复核待办；真实账号挑战与送达未验收。 | 冲突/失败保留输入、凭据变更撤会话、真实邮箱/SMTP。 |
| [31 个人工作台入口](docs/requirement/31-个人工作台入口.md) · [设计](docs/design/31-个人工作台入口.md) · [计划](docs/plan/31-个人工作台入口.md) | 登录工作台复用TopicsWorkspace并保留其他业务入口。 [page.tsx](frontend/src/app/workspace/page.tsx#L23) | 仍有/feeds、/agent等冻结功能入口，按00核对后清理。 | 个人会话隔离、入口可达及窄屏导航。 |
| [32 监控主题工作区](docs/requirement/32-监控主题工作区.md) · [设计](docs/design/32-监控主题工作区.md) · [计划](docs/plan/32-监控主题工作区.md) | 全宽主题列表位于详情上方、默认展开可收起；连续主区与次级结果/运行/设置复用。 [topics-workspace.tsx](frontend/src/app/topics/components/topics-workspace.tsx#L19) | 草稿准入、资料排序、事件状态、24小时趋势和提醒原因分别见CORE-02/05/06/08/10。 | 仅主题区布局、旧tab深链接、草稿/版本冲突与1440px/390px五状态。 |
| [33 新建监控主题](docs/requirement/33-新建监控主题.md) · [设计](docs/design/33-新建监控主题.md) · [计划](docs/plan/33-新建监控主题.md) | 三组词、来源能力、频率/报告配置、语言/窗口/采集上限、q预填和本地预览；新建默认暂停。 [topic-form.tsx](frontend/src/app/monitors/new/components/topic-form.tsx#L84) | 默认暂停已有；来源未就绪保存草稿被服务端拒绝，与新规范不符，见CORE-02。 | q长度、默认状态、草稿保留、重复提交与来源不可用。 |
| [34 监控主题详情](docs/requirement/34-监控主题详情.md) · [设计](docs/design/34-监控主题详情.md) · [计划](docs/plan/34-监控主题详情.md) | 指定主题复用同一TopicsWorkspace与编辑/读取链。 [page.tsx](frontend/src/app/monitors/[topicId]/page.tsx#L5) | 按CORE-02/05/07核对配置、读取和恢复，不能因共用组件认定合同已满足。 | 动态topicId、跨owner、不存在、冲突与恢复。 |
| [35 个人告警](docs/requirement/35-个人告警.md) · [设计](docs/design/35-个人告警.md) · [计划](docs/plan/35-个人告警.md) | 主题/事件选项翻页、规则/版本/目标编辑与最多50条历史。 [alerts-workspace.tsx](frontend/src/app/alerts/components/alerts-workspace.tsx#L429) | 通用负面/热度告警不能替代三类核心提醒；目标验证、静默、关注、语义去重和已读见CORE-09/10。 | 冷却、重复评估、目标修订、未知发送与本人实际收到。 |
| [36 私有资料列表](docs/requirement/36-私有资料列表.md) · [设计](docs/design/36-私有资料列表.md) · [计划](docs/plan/36-私有资料列表.md) | q/来源/主题/日期/分析状态筛选、20条游标，网页采集为显式任务。 [content-list.tsx](frontend/src/app/content/components/content-list.tsx#L140) | 资料目前按UUID翻页；相关性/时效排序见CORE-05，保留观察与真实增量差距见CORE-03。 | 字面搜索、UTC边界、cursor上下文、owner与只读不采集。 |
| [37 私有资料与评论](docs/requirement/37-私有资料与评论.md) · [设计](docs/design/37-私有资料与评论.md) · [计划](docs/plan/37-私有资料与评论.md) | 版本/观察/来源、分析面板与评论根/回复分页，缺父与未加载状态可辨；评论刷新显式受理。 [content-detail.tsx](frontend/src/app/content/[contentId]/components/content-detail.tsx#L369) | 已采评论的独立分析与父链冻结已有；父ID迟到补齐冲突和显式旧帖跟踪见CORE-03/04。 | 回复先到、缺根/父、20条分页、版本引用与评论复采停止。 |
| [38 个人事件列表](docs/requirement/38-个人事件列表.md) · [设计](docs/design/38-个人事件列表.md) · [计划](docs/plan/38-个人事件列表.md) | 个人事件20条分页、热事件独立读取与owner作用域。 [event-list.tsx](frontend/src/app/events/components/event-list.tsx#L52) | 候选状态、解释及排序未完整消费，见CORE-05/06；24小时指标见CORE-08。 | 筛选与排序、边界材料、跨owner及空/错/未知。 |
| [39 个人事件分析](docs/requirement/39-个人事件分析.md) · [设计](docs/design/39-个人事件分析.md) · [计划](docs/plan/39-个人事件分析.md) | 当前/固定修订、20条成员、事实、热度快照和带expected_revision/理由的纠错。 [event-detail.tsx](frontend/src/app/events/[eventId]/components/event-detail.tsx#L40) | 自动事实差分及CAS纠错已有；说法确认/反证状态、继承和可比趋势见CORE-06/08/10。 | 真实事实追溯、并发纠错、撤材料与热度不可比。 |
| [40 平台热榜快照](docs/requirement/40-平台热榜快照.md) · [设计](docs/design/40-平台热榜快照.md) · [计划](docs/plan/40-平台热榜快照.md) | 平台热榜快照与条目各20条，保留原生时间和数值字段。 [hotlist-workspace.tsx](frontend/src/app/hotlists/components/hotlist-workspace.tsx#L113) | 只提供榜单发现，不能替代关键词搜索或跨平台可比热度。 | 真实零/部分、原生单位、来源时间和快照不可变。 |
| [41 个人报告列表](docs/requirement/41-个人报告列表.md) · [设计](docs/design/41-个人报告列表.md) · [计划](docs/plan/41-个人报告列表.md) | 日/周、主题/日期URL筛选、主题选项翻页、20条报告游标及详情入口。 [report-list.tsx](frontend/src/app/reports/components/report-list.tsx#L79) | 新FR/AC全项复核待办；实际生成、自然日报与投递待验收。 | owner、冻结材料、最新修订、日期边界及真实连续生成。 |
| [42 刊期生产档案](docs/requirement/42-刊期生产档案.md) · [设计](docs/design/42-刊期生产档案.md) · [计划](docs/plan/42-刊期生产档案.md) | 内部刊期20条、类型/before_key和显式生产请求，操作ID与版本受理。 [edition-list.tsx](frontend/src/app/editions/components/edition-list.tsx#L23) | 新FR/AC全项复核待办；生产可靠性待验收，优先级在核心之后。 | 幂等/未知受理、窗口重复、失败恢复及任务追溯。 |
| [43 刊期内部详情与修订](docs/requirement/43-刊期内部详情与修订.md) · [设计](docs/design/43-刊期内部详情与修订.md) · [计划](docs/plan/43-刊期内部详情与修订.md) | 固定修订读取、编辑新修订、expected version/操作ID/理由及冲突重读。 [edition-detail.tsx](frontend/src/app/editions/components/edition-detail.tsx#L253) | 新FR/AC全项复核待办。 | 并发修订不覆旧刊、材料撤回、公开/内部边界。 |
| [44 来源连接与采集覆盖](docs/requirement/44-来源连接与采集覆盖.md) · [设计](docs/design/44-来源连接与采集覆盖.md) · [计划](docs/plan/44-来源连接与采集覆盖.md) | 来源能力/连接、Chrome、预算、覆盖窗口与详情/下一步操作。 [sources-workspace.tsx](frontend/src/app/sources/components/sources-workspace.tsx#L12) | 准入及查询回执已有；完整能力分层、来源实例隔离与离线分母见CORE-00/03/07。 | 真实连接版本、到期/风控、应执行分母/漏轮与来源失败隔离。 |
| [45 编辑来源配置](docs/requirement/45-编辑来源配置.md) · [设计](docs/design/45-编辑来源配置.md) · [计划](docs/plan/45-编辑来源配置.md) | 运营令牌内存持有、来源表单/CAS/操作ID、材料/运行读取与显式预览。 [editorial-source-manager.tsx](frontend/src/app/sources/editorial/components/editorial-source-manager.tsx#L95) | 首个来源所需配置先P0；其他编辑来源扩展后置，不默认启用外部预览。 | 准入/预算、草稿冲突、未知写入读回与显式请求边界。 |
| [46 任务记录](docs/requirement/46-任务记录.md) · [设计](docs/design/46-任务记录.md) · [计划](docs/plan/46-任务记录.md) | 20条任务游标、独立连续失败汇总、真实阶段/数量；关键词/评论详情任务累计互斥身份计量见03。 [job-history.tsx](frontend/src/app/jobs/components/job-history.tsx#L81) | 任务累计与lease执行轮差分已有；保留历史删除后新增误判、完整轮次窗口及未知分母见CORE-03。 | 真实排队/执行/失败/取消、漏轮汇总及只读不发请求。 |
| [47 任务详情与恢复](docs/requirement/47-任务详情与恢复.md) · [设计](docs/design/47-任务详情与恢复.md) · [计划](docs/plan/47-任务详情与恢复.md) | 任务详情/刷新、持久取消与按资格手动重试，冻结任务输入和幂等恢复；关键词任务保存查询受理、语言/UTC窗口/有效上限快照，历史未知。 [job-detail.tsx](frontend/src/app/jobs/[jobId]/components/job-detail.tsx#L150) | 采集暂停围栏已有；采集/分析/发送授权分离及未知恢复见CORE-07/10。 | 排队立即取消、执行中停止新请求、lease失效、原job重试与冻结配置。 |
| [48 公开许可与发布管理](docs/requirement/48-公开许可与发布管理.md) · [设计](docs/design/48-公开许可与发布管理.md) · [计划](docs/plan/48-公开许可与发布管理.md) | 运营令牌+会话、来源许可/CAS/理由、覆盖发布与媒体任务/纠错入口。 [publication-manager.tsx](frontend/src/app/publication/manage/components/publication-manager.tsx#L41) | 当前许可全投影、媒体/旧修订/导出及恢复重放见CORE-01；公开关注不得读取私有原始材料。 | 许可收紧、旧修订/媒体/导出失效、公开账号与个人源隔离。 |
| [49 运营工作区](docs/requirement/49-运营工作区.md) · [设计](docs/design/49-运营工作区.md) · [计划](docs/plan/49-运营工作区.md) | 健康/预算/维护、反馈/审计/字典、通知与评测面板已有实现。 [operations-workspace.tsx](frontend/src/app/operations/components/operations-workspace.tsx#L917) | 新核心评测不能用现有精选评测或健康绿灯替代，见CORE-11；预算停用语义见CORE-07。 | 实际权限、持久读写、并发版本/操作ID及故障恢复。 |
| [50 模型配置与成本](docs/requirement/50-模型配置与成本.md) · [设计](docs/design/50-模型配置与成本.md) · [计划](docs/plan/50-模型配置与成本.md) | 模型能力配置/CAS/审计、原币种账本、失败/未知和熔断确认。 [model-manager.tsx](frontend/src/app/operations/models/components/model-manager.tsx#L265) | 按CORE-05/07/11验证本机能力、冻结模型、预算和未知消费；配置入口存在不等于模型或核心闭环已验收。 | 获授权本机模型、切换只影响新任务、限流延后与费用未知不补零。 |

### 站点说明与个人来源

| 编号及文档 | 已有入口（此前源码扫描） | 待补齐 / 待核对 | 待验收 |
|---|---|---|---|
| [51 站点联系配置](docs/requirement/51-站点联系配置.md) · [设计](docs/design/51-站点联系配置.md) · [计划](docs/plan/51-站点联系配置.md) | 联系配置、文字/链接/二维码、版本/理由与显式保存。 [site-manager.tsx](frontend/src/app/site/manage/components/site-manager.tsx#L24) | 新FR/AC全项复核待办。 | 运营权限、并发冲突、公开白名单与配置读回。 |
| [52 意见反馈](docs/requirement/52-意见反馈.md) · [设计](docs/design/52-意见反馈.md) · [计划](docs/plan/52-意见反馈.md) | 5000字反馈、可选联系方式/地址、8MiB图片、内存草稿、显式操作ID提交与失败保留输入。 [feedback-form.tsx](frontend/src/app/feedback/components/feedback-form.tsx#L34) | 接口已有HMAC冷却与附件私有处理；草稿说明需与54对齐，不另立缺失API任务。 | 超限/MIME、重复提交、未知受理、冷却与运营删除附件。 |
| [53 关于](docs/requirement/53-关于.md) · [设计](docs/design/53-关于.md) · [计划](docs/plan/53-关于.md) | 静态关于页与个人非商业、公开/个人数据说明。 [page.tsx](frontend/src/app/about/page.tsx#L7) | 新FR/AC全项复核待办；边界措辞随00核对。 | 可读/键盘/窄屏；不适用远程加载/无权限状态。 |
| [54 隐私说明](docs/requirement/54-隐私说明.md) · [设计](docs/design/54-隐私说明.md) · [计划](docs/plan/54-隐私说明.md) | 会话、本机阅读数据、反馈HMAC/附件与撤许可说明。 [page.tsx](frontend/src/app/privacy/page.tsx#L6) | “反馈草稿保存在浏览器”未区分当前组件内存与持久本机记录，需写清刷新后行为并对齐实现。 | 逐句对照真实保存/清理/导出行为；静态页远程状态不适用。 |
| [55 使用条款](docs/requirement/55-使用条款.md) · [设计](docs/design/55-使用条款.md) · [计划](docs/plan/55-使用条款.md) | 代码/内容许可区分、来源/模型授权和费用边界说明。 [page.tsx](frontend/src/app/terms/page.tsx#L6) | 仍含额度到账预测及统一分发读法，须对齐冻结范围；不能将暂停能力描述为当前完整产品承诺。 | 对照00/08/10与当前实际开关；静态页远程状态不适用。 |
| [56 联系](docs/requirement/56-联系.md) · [设计](docs/design/56-联系.md) · [计划](docs/plan/56-联系.md) | 公开白名单联系配置、未配置空态与二维码读取。 [page.tsx](frontend/src/app/contact/page.tsx#L7) | 新FR/AC全项复核待办。 | 启停、配置失败、二维码当前版本及非公开字段不泄漏。 |
| [57 变更记录](docs/requirement/57-变更记录.md) · [设计](docs/design/57-变更记录.md) · [计划](docs/plan/57-变更记录.md) | 静态日期与变更条目，声明真实渠道/持续运行未通过。 [page.tsx](frontend/src/app/changelog/page.tsx#L6) | 欢迎介绍首页、固定头尾、Codex公告/统一分发与“移植进行中”混在记录中；核实实际发布事实，区分历史行为和当前状态，不把计划当发布。 | 逐项核对可证明的发布内容，不虚构验收或删除未经核实的真实历史。 |
| [58 个人来源](docs/requirement/58-个人来源.md) · [设计](docs/design/58-个人来源.md) · [计划](docs/plan/58-个人来源.md) | 本人RSS/网页/JSON来源、会话owner、默认关闭、CAS/操作ID及未知写入核对。 [personal-source-manager.tsx](frontend/src/app/sources/personal/components/personal-source-manager.tsx#L80) | 不能因URL存在认定可采；个人材料不自动公开的完整链路仍待验证。 | 保存不采集、启用准入/预算、跨owner、版本冲突保草稿及材料/job追溯。 |


## 验证证据与未通过范围

本轮实现核对是源码审查，未重跑业务测试或现场检查部署。此前BACKLOG记录过暂停、查询快照、评论分析、恢复隔离、任务计量、Python质量及登录键盘的受控工程验证；这些结果只覆盖各自切片和当时树，不证明`569ea67c`全量业务回归、当前部署版本或新FR/AC通过。现有测试作为复用入口，不把旧数量汇总成当前通过数。

**部署结构待核对**：此前执行轮切片明确记录，新增执行跟踪、可空上游计数、观察执行归属及FK只在全新独立测试库执行，尚未升级业务库；本轮未检查或改变该状态。推送main不等于服务部署/业务结构已同步。上线前按[PROJECT数据库规则](PROJECT.md#6-数据库)确认现有结构、备份、升级与回滚，不在缺少相应结构的旧库直接运行新代码，也不补造历史轮次归属。此前未配置的Redis/MinIO测试依赖、真实MinIO证据恢复及业务恢复不计通过。

| 范围 | 复用入口 | 本次后续必须补证 |
|---|---|---|
| 草稿/查询/采集 | [test_monitor_topics.py](backend/tests/integration/test_monitor_topics.py)、[test_keyword_discovery.py](backend/tests/integration/test_keyword_discovery.py)、[test_topic_collection_config.py](backend/tests/integration/test_topic_collection_config.py) | 未就绪草稿、确定匹配、未知语言、旧帖跟踪、逐平台真实限制 |
| 身份/增量/执行轮 | [test_content_native_identity.py](backend/tests/integration/test_content_native_identity.py)、[test_content_collection_facts.py](backend/tests/integration/test_content_collection_facts.py)、[test_content_collection_counts.py](backend/tests/unit/test_content_collection_counts.py) | 父ID迟到、删除前观察不误报新增、同轮重复与跨轮、未知归属 |
| 相关性/事件/事实 | [test_analysis_annotations.py](backend/tests/integration/test_analysis_annotations.py)、[test_event_clustering.py](backend/tests/integration/test_event_clustering.py)、[test_event_fact_delta.py](backend/tests/integration/test_event_fact_delta.py)、[test_event_corrections.py](backend/tests/integration/test_event_corrections.py) | 独立维度、排序、候选、确认/反证/纠错、继承；独立保留集质量 |
| 调度/停止/预算 | [test_collection_coverage.py](backend/tests/integration/test_collection_coverage.py)、[test_topic_collection_pause.py](backend/tests/integration/test_topic_collection_pause.py)、[test_resource_budgets.py](backend/tests/integration/test_resource_budgets.py) | 离线跨政策完整分母、独立停止作用域、预算停用及不清额度 |
| 目标/告警/外部unknown | [test_alerts.py](backend/tests/integration/test_alerts.py)、[test_notifications_pipeline.py](backend/tests/integration/test_notifications_pipeline.py) | 地址挑战、静默、三类触发、关注取消/继承、跨版本语义去重与本人接收 |
| 权限/身份/恢复 | [test_resource_isolation.py](backend/tests/integration/test_resource_isolation.py)、[test_content_dependency_cleanup.py](backend/tests/integration/test_content_dependency_cleanup.py)、[test_identity_login.py](backend/tests/integration/test_identity_login.py)、[test_restore_isolation.py](backend/tests/integration/test_restore_isolation.py) | 全投影当前许可、跨存储失败恢复、独立删除账本重放及上线隔离；MinIO/真实业务恢复另验 |

**未通过的产品验收**：真实两轮国内来源采集、独立相关性/事件评测、完整消费链就绪后的七个连续自然日、全部应执行窗口及至少一次自然提醒本人接收，均未由本轮证明。当前部署与该提交对应关系未检查；受控页面/固定样本/健康检查不替代登录后核心页面和真实依赖验收。超预算、未准入、越权、误去重、停止作用域新请求等硬门槛任一失败即阻断。

## 核心之后的P1/P2

- [ ] **P1 扩展来源与发现**：已冻结核心国内POC清单的能力、准入和真实验收仍属CORE-00/11的P0范围；超出该范围的新增平台再按P1逐项评审。每个来源独立验证搜索、评论/回复、身份/增量、事件质量及自然运行，不用单个B站或HN通过代替国内POC。海外目标保留，依据免费能力和批准条件决定次序。
- [ ] **P1 报告与知识利用**：核对日报/周报、模型不可用模板降级、验证订阅/退订、单向Obsidian导出和材料许可；引文问答先验证价值及隐私。现有页面或任务不能替代生成/降级/接收证据。
- [ ] **P1/P2 辅助能力**：按12～58矩阵重评公开阅读、检索、模型榜、刊期生产和站点说明；核心依赖、安全泄漏及阻断故障立即回到P0。情感/观点扩展、视觉和排名历史等不挤占核心闭环。
- [ ] **冻结范围清理**：逐消费者核对Codex公告/统一分发等残留入口和实现；先确认数据、恢复与引用影响，再退役。默认关闭不等于已清理，也不构成解冻授权。
