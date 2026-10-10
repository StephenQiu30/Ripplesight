# 文档验证记录

## 2026-10-10 独立浏览器退役与SQL目录改名

核查远程BrowserRuntime仅有探测CLI与专用测试调用，业务采集没有消费者。按用户要求移除独立browser/browser-egress及相关运行时、配置、探测和专用测试；保留会话凭据兼容及报告导出Playwright用途。backend/database改为backend/sql，schema逐字一致，Docker、初始化、维护/CLI备份恢复、CI、测试和现行文档引用已同步。ruff、format、mypy、普通pytest1606通过/954跳过；另用独立PostgreSQL18空库和临时MinIO完成schema及备份恢复10项测试，零跳过，资源已清理。开发/生产Compose一致性与凭据隔离断言、后端镜像构建和独立审查通过。详情与验证边界见[验收记录](records/2026-10-10-独立浏览器退役与SQL目录改名.md)。

## 2026-10-10 旧脚本删除与检查入口整合

用户确认保留7个旧文件删除并调整检查入口。ESLint设计规则并入配置；文档工具迁到frontend/tests/docs共用前端依赖与锁文件；openapi:check直接重新生成并拒绝HEAD差异、暂存变化和未跟踪文件。原工作区lint、typecheck、format:check、build及128文件1037项测试通过；本机独立API仅导出当前源码的契约，关闭lifespan且不访问业务数据库，客户端无漂移。首次全量测试与契约生成并行，生成器重写API目录时造成一个套件导入失败；生成结束后顺序全量复跑通过。独立复审通过，文档检查入口和CI路径已同步。未改业务UI、接口或数据库，未重跑浏览器及后端验收。详见[验收记录](records/2026-10-10-旧脚本删除与检查入口整合.md)。

## 2026-10-10 菜单与工作台提交验证

按用户授权将账户/更多菜单及工作台布局修正分别提交main。基于HEAD和19个交付文件导出的合并快照，lint、typecheck、format:check、build及126文件1023项测试全部通过；文档索引无变化，124份文档检查通过。独立只读审查未发现阻断问题。本轮未重新执行浏览器验收，沿用下方记录中的历史受控UI证据；未改后端、接口或数据库。共享工作区的frontend/scripts与scripts/docs删除不纳入提交，快照保留HEAD校验脚本，检查结果不代表共享工作区完整门槛通过。

## 工作台布局与页面恢复（2026-10-10）

用户指出很多页面需要恢复，已撤回此前全站单列实现；53文件恢复本轮布局前快照，保留工作台列表先于详情及草稿交互。DESIGN和PRD取消强制全站单列，页面需求恢复原响应式结构。此前1038项与全站单列浏览器结果属于已撤回方案，恢复后隔离快照build、typecheck、lint、format:check和1035项测试、独立只读审查通过；13代表页面×1440/390共26次扫描无溢出与未捕获异常，工作台/探索双尺寸五状态、工作台键盘与草稿保留22例复验通过，正文axe零违规。scripts/docs的pnpm index与pnpm check通过，123份文档有效。证据见[验收记录](records/2026-10-10-工作台布局与页面恢复.md)。

## 页头与空状态统一（2026-10-10）

模型榜空态移除冗余说明和请求ID，普通页头及详情面包屑复用PageHeader。当前工作区类型、格式、生产构建和独立审查通过；1440px/390px共用组件五状态、真实榜单空态/来源目录及768px/1024px首页换行与键盘导航通过，来源页头axe检查零违规。原工作区缺失校验脚本仍阻塞lint及配置测试；保留HEAD脚本的临时副本lint零警告、格式及126文件1034项测试通过，不替代原工作区门槛。docs索引/check最终通过，证据和限制见[验收记录](records/2026-10-10-页头与空状态统一.md)。

用户授权提交main后，以实际暂存树独立复核：lint、类型、格式、build与126文件1031项测试通过，文档index无漂移、121份check通过。保留Git中的校验脚本，账户菜单等并行修改未纳入；减少的3项测试属于并行菜单切片。

## 全局普通加载指示（2026-10-10）

依据用户纠正更新DESIGN加载规则、BACKLOG及[验收记录](records/2026-10-10-全局普通加载指示.md)。普通Spinner的隔离工程检查、双尺寸浏览器与独立审查通过；共享工作区的并行脚本删除及格式问题仍明确保留。scripts/docs的pnpm index和pnpm check通过，120份文档的元数据、命名、索引和本地链接有效，不构建文档站。

## GSAP交互过渡（2026-10-08）

验收见[记录](records/2026-10-08-GSAP交互过渡验收.md)：更新frontend/DESIGN、BACKLOG、公开阅读能力的局部证据，保持整体部分可用。scripts/docs下pnpm index与check通过，116份文档的元数据、命名、索引及本地链接有效；不构建已退役的文档网站。

2026-10-08 起文档位于 docs，在线知识库已退役。下方保留既有站点/内部知识库/业务验收证据，其中旧命令与运行状态均为历史记录，不代表当前设施仍存在。当前使用方式见 [README](README.md)。

# 文档网站验证记录


## CI生产底线修复（2026-10-08）

远端原runtime [37738855513](https://github.com/StephenQiu30/Ripplesight/actions/runs/37738855513)在生产文档镜像中的Git元数据依赖失败；原backend [37727825324](https://github.com/StephenQiu30/Ripplesight/actions/runs/37727825324)有17失败、2556通过、6浏览器沙箱项跳过。此前普通pytest/专项通过不能代表全量CI通过。

本轮修复embedding计费接口字段遗漏；可见性读取保留最后明确来源结论，超时不撤权、删除/受限不因后续失败恢复；media_only按已授权实际语义字段复核。详情/检索/覆盖fixture补齐真实observation清单、signature、原Evidence及完整job scope。X确认删除后的旧200正文断言与生效决策06冲突，改为404且不可泄露文本；超时前版本及可见性历史断言保留，并加入deleted→timeout、restricted→unknown与媒体字段撤权回归。语义样本时间移入真实14天窗，新增窗边界及最近接收不刷新旧发布时间回归。

CI仍使用实际锁定运行栈；移除旧卷名兼容检查和重复全套Web/startup测试。后端248文件按83/83/82划分至三个隔离运行环境，全套无遗漏或重叠，失败不取消其他分片；JUnit保留证据，除现有六个浏览器沙箱用例外的skip阻断通过。六项需要专门远程浏览器/出口沙箱，仍明确未在普通CI执行；不是数据库/消息/对象存储缺失的豁免。contract保留运行API生成漂移和53专项，frontend全量交互/静态/构建，runtime生产依赖/代理/会话/CSRF/CSP/Worker/非root只读边界，Workspace校验/工具测试/构建/发布均保留，支持按SHA手动重验。

本机证据：Ruff及721文件格式检查通过、mypy440源文件通过；1596单元/架构测试通过；原59数据库定向项通过，新增边界与相关模块51项通过（两组有重叠，不相加）；contract53项通过；文档26工具测试/类型检查及114页构建通过。隔离库hotkey_test_ci_fix_20261008用唯一schema初始化，未操作业务库；生产镜像构建及远端最终SHA结果以随后CI记录和交付链接为准。独立subagent只读审查及embedding10项/workspace7项复核通过，要求的六名称skip白名单已采纳。

代码提交[c8f2f1f8](https://github.com/StephenQiu30/Ripplesight/commit/c8f2f1f861c2beac49ba4061388c120b70165132)已推送main，同一SHA远端结果如下。三份JUnit共2584个唯一用例，无遗漏/重叠；2578通过、零失败/错误，6个已登记浏览器沙箱用例未执行。分片分别852/782/950项，耗时931/928/1257秒；backend整条工作流约24分16秒，原失败运行pytest约47分56秒，本次观测只用于比较并行耗时，不声明性能SLA。

| 工作流 | 远端证据 | 结果 |
|---|---|---|
| backend | [37740914447](https://github.com/StephenQiu30/Ripplesight/actions/runs/37740914447) | 三个独立服务分片全部成功；静态检查及意外skip保护通过 |
| frontend | [37740914381](https://github.com/StephenQiu30/Ripplesight/actions/runs/37740914381) | 125文件1028项、lint/双类型/格式/build全部成功 |
| contract | [37740914441](https://github.com/StephenQiu30/Ripplesight/actions/runs/37740914441) | 同提交运行API生成漂移与53专项成功 |
| runtime | [37740914351](https://github.com/StephenQiu30/Ripplesight/actions/runs/37740914351) | 生产构建、schema/SQL/Redis/Kafka、代理/Worker、登录/CSRF/动态nonce/注销、非root只读成功 |
| Workspace site | [37740914406](https://github.com/StephenQiu30/Ripplesight/actions/runs/37740914406) | 内容/26工具测试/类型、114页构建与Pages发布成功 |

本机生产文档builder在不携带.git的Docker上下文内实际构建与check成功；skip保护负向验证确认数据库skip、新增未登记浏览器skip、缺失依赖环境都拒绝通过。隔离数据库及验证镜像已删除。完整原始日志/JUnit保存在本机/tmp/ripplesight-ci-*及远端backend-tests-0/1/2 artifacts；最终归档只更改BACKLOG和本记录，不更改已验代码或CI配置，按其受影响工作流重新检查。本轮未操作业务数据库；CI通过不替代已有Figma/真实提供方/长期送达验收边界。

## 2026-10-08 subagent独立审查与全站验收

本轮从main/origin/main均为bf72cfe3、工作区干净开始。本人允许一名独立subagent替代Claude并继续agent-browser验收与修复；历史Claude登录过期不再是本轮门槛。永久逐页证据见[全站验收矩阵](product/reference/16-全站验收矩阵.md)与[验收记录](records/2026-10-08-subagent全站验收.md)。

| 检查 | 结果与边界 |
|---|---|
| Web | lint、双tsconfig类型、format:check、125文件1028项测试及生产build通过；无后端/schema/生成API变更 |
| 测试执行 | 最终pnpm test --maxWorkers=2 --testTimeout=30000；初次默认5秒的design-system ESLint冷启动超时，如实保留。未修改Vitest配置、断言或跳过项 |
| 独立审查 | 同一只读subagent多轮复核；最终来源/Chrome9项、公告/刊期交错21项、配置/加载增量22项专项及相关ESLint、完整类型检查通过；批次重叠不相加 |
| 页面矩阵 | 52代表路由×1440/390正常104例；零记录/503/403注入312例，共416扫描；修复后重扫受影响页面，零axe违规/横向溢出/未捕获异常。incomplete仍保留，不等同全量可访问性通过 |
| 交互 | 四列表分页撤权8例、来源Sheet撤权/恢复焦点2例、公告/热榜分页撤权6例、报告连续日期修改/刷新恢复及探索翻页4例；390×844通过Tab进入正文、PageDown在加载期间滚动 |
| 加载 | 首页/探索经可见导航捕获SSR加载4例；客户端加载52次尝试中38例捕获实际busy/status，零axe违规/溢出；14例未捕获/不适用单列于逐页证据，静态/令牌/空表单无等待不当作已验 |
| 文档 | index、check（26项工具测试及TypeScript）、112页build通过；112页HTTP正文、原文/AI导出与中文检索核对通过 |
| 真实服务 | 8666的52代表路由HTTP访问成功，27个私有路径匿名重定向login；API ready200、公开事件零记录、模型榜未发布404、匿名会话401；未改真实认证、未写业务库 |
| 边界 | 原稿统计/情感/历史曲线/X趋势、完整收藏类型等服务缺口未通过；5个运营令牌入口未验管理数据/写入，真实登录/编选/外发/来源长期运行/送达/恢复容量未验；5项历史数据库失败仍在BACKLOG |

修复包含探索词带入草稿、关键词空时禁用排序、分页回正文顶部、报告URL同步；私有列表与来源撤权清除旧结果；公告读取/版本探测和刊期编选使用共享代次防迟到回填；403→503不恢复未知的编选权限；统一加载骨架/减少动画、正文键盘可滚动、列表与命名group语义、刊期错误状态。所有修复经相应回归与独立复核，不把模拟数据视作真实能力。

文档第一次HTTP原文校验赶上容器热更新仍在发布上一快照，矩阵原文与本机不一致；等待新快照完成后，两份新文档原文逐字匹配，重新执行verify通过。没有放宽原文断言。

隔离只读8766/8767固定样本采用合成会话，写请求405；原始矩阵、DOM、截图和脚本在忽略目录.tools/fullsite-acceptance-20261008/，检查日志在/tmp/ripplesight-*。只关闭本轮浏览器和临时预览，8666/8667/8668及其他项目服务保留。

## 2026-10-08 设计审查问题修复

修复前快照为58817e7d。修改探索、公开事件时间线、登录语义、榜单空态和开发配置；需求和证据登记在现有页面文档与[修复记录](records/2026-10-08-设计审查问题修复.md)。没有改业务schema、真实认证或冻结App。

| 检查 | 结果与边界 |
|---|---|
| Web | lint、typecheck、format:check、124文件974项测试、生产build通过 |
| 后端 | ruff check/format、440文件mypy通过；普通pytest：1626项通过、953项明确跳过；完整数据库集成没有通过 |
| 数据库合同 | 独立hotkey_test_design_fixes_20261008执行canonical schema；榜单3项、HTTP合同10项、读取单元2项共15项通过，库已删除；含无发布404与依赖503区分 |
| 扩展数据库检查 | 349项通过/16项跳过时发现5项历史失败并停止，不能称全量通过；修复前HEAD原始backend快照上5项全部复现 |
| 契约 | 同提交热更新API后重新生成客户端并openapi:check无差异；只改错误语义和描述，无新增响应字段 |
| 文档 | index、check（26项工具测试和TypeScript）、build通过；110页正文、原文/AI导出和Pagefind索引生成 |
| 开发稳定性 | 缓存移出tmpfs后webpack仍达到堆阈值主动重启；切换Turbopack后52个代表路由均200，无OOM/容器重启，三个服务健康；峰值约2.84GiB，空闲约0.83GiB，长期容量未验收 |
| 浏览器 | 1440/390复核探索、事件、榜单、登录，共8组核心布局；来源状态用键盘Enter展开，登录跳转主内容可用；提醒红色对浅色背景为4.86:1；探索正常/空/错误/无权限及事件时间线加载共10例均无横向溢出；完整逐页五状态未验收 |
| 独立审查 | Claude CLI返回Login expired，未取得审查，按AGENTS§6不记正式代码完成或能力可用 |

最终axe复扫：探索、事件和登录的1440/390均零违规、零待人工确认；榜单390零违规、零待确认，1440零违规、有1项对比度待确认（4个分数的背景被判断为遮挡）。滚动后8个分数均实际可见，读取前景rgb(23,23,23)与白色背景，人工复算17.93:1；不把该自动待确认项改写为自动通过。专题计数和事实引用已改为可命名的group语义。

历史数据库失败：test_collection_coverage_http的analysis_anomaly/unknown区分；test_content_records的可见性历史、media_only和当前规则annotation投影；test_content_search的analysis_state过滤。修复前后均失败，单独列入BACKLOG，不删断言或改变许可规则掩盖。临时原始快照已清理；日志和截图位于忽略目录.tools/agent-browser-fix-review/及本机/tmp/ripplesight-fix-*.log。

以下原始记录保留历史上下文，不作为当前 checkout 或线上部署的证明。本轮重新执行的结果见文末。

## 原始记录

核验日期：2026-10-06。仓库 HEAD 仍为 `b8b76234`；未提交、未推送，未设置 GitHub Pages。`backend/`、`frontend/` 和既有 `.codex/` 删除不在本次修改范围。

环境：Node `v24.19.0`，运行脚本的 pnpm `12.3.4`。安装了 npm registry 当前稳定版本 Nextra/theme `4.6.1`、Next `16.3.8`、React/React DOM `19.3.0`；TypeScript `5.9.3` 与前端保持同一主版本。

下列命令在 `workspace/` 执行。沙箱不允许写入用户级包管理器缓存，因此命令使用 `PNPM_HOME=/private/tmp/hotkey-docs-pnpm`；首次安装同时使用 `npm_config_cache=/private/tmp/hotkey-docs-npm`。未覆盖 HTTP(S)_PROXY。

| 命令 | 结果 |
|---|---|
| `npm_config_cache=/private/tmp/hotkey-docs-npm PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm install --store-dir /private/tmp/hotkey-docs-store` | 成功，pnpm 12.3.4；生成独立锁文件 |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm install --frozen-lockfile --store-dir /private/tmp/hotkey-docs-store` | 退出 0；锁文件验证 495 项，无需解析更新 |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm index` | 退出 0；“索引已是最新，无改动。” |
| `git diff --exit-code -- content/index.md` | 退出 0，无输出 |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm check` | 退出 0；24 个发布页面；8 个回归用例通过；TypeScript 通过 |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm build` | 退出 0；24 个文档静态页面；Pagefind 索引 24 页、1559 个词、zh 单语言 |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm preview` | 启动 `http://127.0.0.1:8668/hotkey-server/` |
| `PNPM_HOME=/private/tmp/hotkey-docs-pnpm pnpm verify` | 退出 0；24 个页面与原文均返回 200；导航、元数据、全文嵌入、改写链接和 AI 导出断言通过 |

`pnpm verify` 使用导出的 `out/_pagefind/pagefind.js` API，在 Node 中经 HTTP 加载真实索引。采用与 Nextra Search 相同的 `baseUrl: '/'`，验证结果链接挂载到 `/hotkey-server` 后能返回 200。

| 查询 | 结果数 | 首条结果 |
|---|---|---|
| 舆情 | 12 | 舆情监控开源方案调研 |
| 评论 | 14 | 04 评论舆情 |
| 情感 | 8 | 04 评论舆情 |

显式 curl 命令如下，四条均退出 0、返回 HTTP 200：

```sh
curl --noproxy '*' -fsS -o /private/tmp/hotkey-docs-home.html -w 'home HTTP %{http_code}\n' http://127.0.0.1:8668/hotkey-server/
curl --noproxy '*' -fsS -o /private/tmp/hotkey-docs-capability.html -w '评论舆情 HTTP %{http_code}\n' 'http://127.0.0.1:8668/hotkey-server/capabilities/04-%E8%AF%84%E8%AE%BA%E8%88%86%E6%83%85/'
curl --noproxy '*' -fsS -o /private/tmp/hotkey-docs-progress.html -w '进度 HTTP %{http_code}\n' 'http://127.0.0.1:8668/hotkey-server/product/02-%E8%BF%9B%E5%BA%A6%E4%B8%8E%E4%BC%98%E5%85%88%E7%BA%A7/'
curl --noproxy '*' -fsS -o /private/tmp/hotkey-docs-llms.txt -w 'llms.txt HTTP %{http_code}\n' http://127.0.0.1:8668/hotkey-server/llms.txt
```

进度页 HTML 包含 `HotKey BACKLOG` 到“由 Claude 写任务卡并派给 Codex 开发”的末节正文。能力链接为 `/hotkey-server/capabilities/04-评论舆情/`（编码形式也可访问），工程规范链接为 `https://github.com/StephenQiu30/hotkey-server/blob/main/AGENTS.md`。技术架构页包含 PROJECT 的技术栈、数据库、配置与部署等章节。回归用例还核对了 `backend/README.md` 和 `PROJECT.md#6-数据库` 的 GitHub 改写与锚点保留。

已列出和核对的产物：

```text
out/llms.txt                                8597 bytes
out/llms-full.txt                          62299 bytes
out/_pagefind/
out/_pagefind/pagefind.js                  45555 bytes
out/capabilities/04-评论舆情/index.html
out/raw/capabilities/04-评论舆情.md           3413 bytes
```

HTML 使用 Markdown 模式编译，保留首页 HTML 注释标记，首页与写作规则不需要改动。模板、看板和 `.obsidian` 没有生成路由或 AI 原文；Pagefind 只索引发布正文。Nextra 的 Layout 校验缺陷通过持久 pnpm 补丁修复，补丁同时翻译主题无法配置的五处 UI/无障碍标签；详见 README 与 THIRD_PARTY_NOTICES。

在仓库根目录执行 `git diff --check` 通过；`git diff --exit-code -- docs/index.md BACKLOG.md` 无输出；`git diff --summary -- docs` 无输出，未重命名或移动内容文件。工作流 YAML 的事件和 Pages 权限已解析验证。

新增文件：

- `.github/workflows/workspace-site.yml`
- `workspace/.node-version`、`.npmrc`、`package.json`、`pnpm-lock.yaml`、`pnpm-workspace.yaml`、`tsconfig.json`、`next.config.mjs`
- `workspace/app/layout.tsx`、`app/[[...slug]]/page.tsx`、`app/not-found.tsx`、`app/style.css`、`mdx-components.tsx`
- `workspace/scripts/content.mjs`、`content.d.mts`、`navigation.mjs`、`index.mjs`、`check.mjs`、`export.mjs`、`preview.mjs`、`verify.mjs`
- `workspace/tests/docs.test.mjs`、`patches/nextra-theme-docs@4.6.1.patch`、`README.md`、`VERIFICATION.md`

修改文件：`.gitignore`、`AGENTS.md`、根 `README.md`、`PROJECT.md`、`THIRD_PARTY_NOTICES.md`，以及 `docs/product/02-进度与优先级.md`、`03-技术架构.md`（只移除旧 include 注释，保留 source 和 Obsidian 原文链接）。生成的 node_modules、.next、out、next-env.d.ts 不纳入版本控制。

尚未验证：桌面、390px 窄屏、键盘和浏览器搜索交互，以及真实 GitHub Actions/Pages 部署。浏览器工具对 `http://127.0.0.1:8668` 的访问被自动审批拒绝，工具理由为该地址未获用户授权；未绕过该拒绝。Node 查询和静态 HTTP 验证不等同于浏览器交互验收。仓库所有者仍需在 Settings → Pages → Source 选择 GitHub Actions。


## 本轮工具修复与编号复核

日期：2026-10-06。文档分类与编号修正已在 main 的 `286e4dbe` 提交并推送；以下检查针对其后的工作目录实现，包含本轮未提交修改，不冒充已发布快照。恢复缺失的脚本、测试与主题补丁后，重新执行当前检查；原始记录中的旧路径和浏览器审批结果不代表本轮状态。

产品编号按目录独立：`product/` 的进度、架构、工程规范依次为 01、02、03；`product/prd/` 的总 PRD、专项 PRD 为 01、02；`product/plan/` 的专项 PLAN 为 01。同目录重复编号、00、非英文目录及 PRD/PLAN 放错目录会拒绝。索引、导航、原文导出使用当前路径。

| 本轮检查 | 结果 |
|---|---|
| 冻结锁文件安装 | 退出 0；恢复并应用已登记的 Nextra/theme 4.6.1 补丁 |
| `pnpm index` | 生成 27 页清单的分类索引；二次生成无改动 |
| `pnpm check` | 27 个公开页面；13 个回归测试通过；TypeScript 通过 |
| `pnpm build` | 退出 0；27 个文档页面、中文 Pagefind 索引、逐页原文与 AI 导出生成 |
| `pnpm preview` + `pnpm verify` | 退出 0；27 页正文与原文 HTTP 200，导航、PLAN 元数据、根文件嵌入、链接及 AI 导出通过 |
| 中文查询 | 舆情 12 条、评论 14 条、情感 8 条；属于预览冒烟检查，不等于专项 KR3/KR4 |
| 桌面浏览器 | 分类导航、PLAN 元数据、中文搜索、无结果反馈、搜索加载反馈、方向键和回车打开命中章节、Escape 收起结果通过；专项 PRD 的 Mermaid 图完成渲染，未捕获浏览器 error/warn |
| 390px 窄屏浏览器 | 菜单可打开分类与 PLAN，正文和表格可读；页面宽度未超过可用视口；检查后恢复默认视口 |
| 公开内容边界 | 只导出显式清单；未登记私密/草稿样本不进入目录、原文或 AI 全文；错误登记、重复路径、缺失文件与符号链接越界拒绝；移除旧 raw 导出；模板引用不导出模板正文 |

预览地址为 `http://127.0.0.1:8668/hotkey-server/`。截图保存在当前 Codex 任务附件目录，不作为知识库作者原文。当前浏览器正常读取本地预览；本轮未发生原始记录所述的审批拒绝。

本轮没有启用或验收 GitHub Pages；没有接入 frontend `/workspace/docs`、服务端文档权限、真实 Obsidian 双端同步或 AI 问题集。静态预览无应用登录权限状态，不能据此声称通过专项 KR2。Claude 审查仍待进行，工具任务未标记为“代码完成”或“能力可用”。


## 接入方案草案复核

同日，工具实现已在 `8d562ced` 推送 main。随后根据当前源码整理 PROJECT §11，并新增 `capabilities/07-项目文档知识库.md`，明确专项 KR 的归属；以下是新增文档后的工作目录检查，不构成权限或业务功能验收。

- `pnpm index` 更新能力清单，二次生成无改动。
- `pnpm check` 退出 0：28 个公开预览页面，13 个测试与 TypeScript 通过。
- `pnpm build` 退出 0：28 个文档页面、28 页中文索引（2150 个词）与 Markdown/AI 导出生成。
- `pnpm verify` 退出 0：28 页正文与原文、根文件嵌入、链接、导航、元数据和中文查询通过。
- 最终构建后重新加载浏览器首页并保存分类预览截图；此次增加方案文档，没有修改应用 UI 或接口。

本轮公开预览文件增加的是方案与规格，不含账号 UUID、凭据或私密正文。正式环境与本人账号已请求确认；Claude 审查仍待进行，后续快照、接口与页面按 PLAN 准入。没有取得工具提交对应的 GitHub Actions 运行证据，以上结论限于本地工程和浏览器检查。

## 本机知识库接入验证

日期：2026-10-06。用户确认保留 Nextra，并仅在本机启动。本轮实现尚未提交或推送；既有 frontend 重设计的并行修改原样保留。以下结论针对当前工作目录，不能作为 main、CI 或真实使用验收的证明。

| 检查 | 结果与边界 |
|---|---|
| 后端 Ruff、格式、mypy | 全部退出 0；713 个文件格式通过，435 个源文件类型检查通过 |
| 后端 pytest | 1613 通过、948 跳过；未提供独立 PostgreSQL 测试库，跳过项不算通过，没有修改数据库结构 |
| frontend lint、typecheck、format:check | 全部退出 0 |
| frontend test | 92 个文件、607 项通过；包含真实 Editor.js ESM 加载、保存与未知 Markdown 字节保留，以及 Nextra 编译、章节和安全渲染 |
| frontend build | 退出 0；目录和详情为动态授权路由，不把内部正文编入公开产物 |
| OpenAPI | 同一工作目录的 API 在独立本机端口运行，重新生成客户端；openapi:check 退出 0，生成前后文件指纹一致 |
| workspace check、build | 29 个公开页面、19 个测试与 TypeScript 通过；Nextra/theme、Pagefind 中文索引、逐页 Markdown 和 AI 导出仍仅来自公开清单 |
| 独立 Git 工具测试 | 确定性、根文件映射、正文及章节 hash、快照损坏拒绝、重复保存、草稿恢复、冲突合并、限定提交、失败保留、决策替代、历史附件、路径及符号链接校验、提交后结果恢复均通过 |
| 本机初始化与只读 CLI | local:init 使用隔离目录创建专用副本与 30 篇内部文档快照，副本无 origin，配置和状态文件 0600、目录 0700；list/search/read 能读取已发布版本 |
| Git 工作目录检查 | git diff --check 退出 0；没有移动或重命名作者内容，没有向当前开发 checkout 提交或推送 |

浏览器使用现有前端生产构建和真实文档服务、Node 发布工具，但身份由仓库外的受控样本提供；来源、草稿与操作均在独立临时 Git 副本。没有使用本人真实登录，也没有向业务数据库写测试数据。测试端口为 Web 18866、API 18768，仅监听本机；产品仍使用约定的 8666/8667。

- 桌面与 390px 均检查正常、空、加载、错误、无权限状态。窄屏目录和正文宽度为 390px，没有整页横向溢出；表格自行横向滚动。Tab 到检索按钮、Enter 检索及打开命中章节通过，章节进入应用滚动容器并获得焦点。
- 富文本修改切换到原文视图、保存草稿、确认发布通过。隔离副本首个发布的 Git 差异只有预期段落的一处修改，来源干净，目录、详情与读取快照整体切换。
- 浏览器编辑期间从文件侧改变来源，保存返回版本冲突，网页未保存内容与本地来源分别保留。明确合并后再次保存和发布，正文同时包含两侧修改。
- 决策替代只在隔离副本执行。默认目录隐藏旧决策；启用历史模式可读取其废弃状态，编辑入口隐藏，关联新决策和原文链接保留 snapshot/history。发布工具测试另核对旧附件默认隐藏、历史模式可读。
- 浏览器检查期间发现并修复中文路由解码、重复章节提取、Editor.js 的 LogLevels 仅类型导出及保存器原文清理、跨路由章节定位问题。最终受控页面未捕获 error/warn。中文输入采用受控填充，不能替代实际输入法组合输入验收。

截图保存在当前任务附件目录。受控身份、假数据入口及临时发布内容都没有加入产品代码或公开清单，验证结束关闭本轮临时进程，保留原本运行的服务。

未完成门槛：真实账号 UUID 与正式本机初始化、真实 Obsidian 的五类十次往返、实际输入法、固定 20 条检索与 20 个本机 Codex 问题、目标环境完整冷启动与恢复。已尝试本机 Claude 只读审查，CLI 返回登录过期，审查没有执行。按 AGENTS §6，当前不标记“代码完成”或“能力可用”；没有本轮远端 CI 证据。Mermaid 内部页面显示可编辑源码，公开 Nextra 预览的图表渲染继续保留。

## 2026-10-07 需求 workspace 阅读验证

范围：按用户本轮要求，先搭需求阅读与核对 workspace，暂不实现业务代码；文档与执行以最小 POC/demo 为后续验证方式。基于 main 的 `5e098e86` 工作目录，修改未提交或推送。复用现有 Nextra 静态阅读工具，没有新增应用、接口、数据库结构、编辑器或同步实现。

新增原文：[需求与验证入口](product/reference/04-需求与验证入口.md)、[AI 任务协议](product/reference/05-AI任务协议.md)、[POC 验证卡](product/reference/06-POC验证卡.md)、[热点事件候选核对](research/2026-10-07-热点事件需求核对.md)。首页改为先读当前需求与验证方式；根 AGENTS/BACKLOG 记录当前阶段，workspace/AGENTS 指向最小阅读路径。已有 PRD、决策、能力和大计划原文保留，不自动废弃或派发。

| 检查 | 实际结果 |
|---|---|
| `pnpm index` | 退出 0；首页生成索引包含新增阅读页 |
| `pnpm check` | 退出 0；34 页元数据/链接/命名有效，19 个现有工具测试与 TypeScript 通过 |
| `pnpm build` | 退出 0；34 页静态正文、34 页 Pagefind 中文索引与原始 Markdown / AI 导出生成 |
| `pnpm preview` | 已启动；仅监听 127.0.0.1:8668，阅读入口为 `http://127.0.0.1:8668/hotkey-server/` |
| `pnpm verify` | 最终退出 0；34 页正文和原文、导航、根文件嵌入、链接与 AI 导出有效；舆情 13 条、评论 16 条、情感 10 条 |
| 实际浏览器 | 首页显示当前阶段；打开需求原话、AI 协议与热点候选；搜索 POC 后点击第一条打开验证卡；候选明确标为待核对、未执行，卡保留待执行结果 |
| 当前 Codex 原文读取 | 直接读取本机 `out/raw/` 的需求入口、AI 协议与候选；以下三项核对可回到作者原文 |

原文核对问题与答案：

1. 当前是否可以开始业务编码？不能；本轮阶段是 workspace 搭建与需求核对（需求入口“用户已经明确的要求”）。
2. 首个热点 POC 是否已被选定或跑通？没有；它是待核对的 AI 候选，尚无业务验证结果（候选页开头）。
3. 工程检查通过是否等于真实业务能力可用？不等于；证据等级与局限需要区分，验证卡通过不自动更新整项能力为可用（AI 协议“文档状态不能代替验证”“执行和交付”）。

首次 `pnpm verify` 因 PROJECT 缺少“文档预览”说明而失败；在 PROJECT §10 补上当前实际使用的本机入口、作者来源与边界后，重新构建并复验通过。未修改验证脚本或放宽断言。

首页截图保存于本机忽略目录 `.tools/requirements-workspace/2026-10-07-home.jpg`；浏览器阅读标签页保留。重启预览在 workspace 执行 `pnpm preview`，内容改动后先重新 build。

边界：本次只验证文档阅读、检索、原文导出与当前 AI 的三条事实核对，尚未取得本人阅读反馈；没有选择或执行业务 POC，没有真实在线采集或模型调用，没有启动正式 `/workspace/docs` 的专用来源与账号配置，也没有实际 Obsidian 双端验收。当前作者目录仍是开发 checkout 的 `docs/`。`llms.txt` 中的绝对 URL 仍指向既有 GitHub Pages，本轮新内容仅在本机，AI 应读当前本机文件或 8668 原文。没有对外发布，也没有改动已有业务服务和自动化配置。


## 2026-10-07 产品参考英文目录修正

按用户要求，将 product 根层六份参考文档移入 `content/product/reference/`，与 `prd/`、`plan/` 并列；保留文件名和编号。更新相对链接、根文件 source、related、公开/内部清单、AI 入口与架构目录说明。现有文档工具只调整目录分组、导航与指针路径，并同步现有测试/验证脚本中的路径；没有业务实现。

`pnpm index`、`pnpm check`（34 页、19 个工具测试及 TypeScript）、`pnpm build`、`pnpm verify`（34 页正文/原文与 AI 导出）、`git diff --check` 均通过。浏览器重新加载首页，产品参考为独立分组，分类表显示 `product/reference/`；新页面与 raw 路径在 HTTP 验证中通过。旧编号历史文字保留，新原文导出使用迁移后的目录。截图：`.tools/requirements-workspace/2026-10-07-product-reference.jpg`。未提交、推送或对外发布。

## 2026-10-07 页脚与项目显示名称

核对 workspace/app/layout.tsx 及当前安装的 nextra-theme-docs 源码：全局 Footer 为 Nextra 内置组件，页脚文字由本项目配置，Layout 的 footer 参数为可选。本轮删除该组件的导入与配置。项目显示名沿用现有 frontend 的“知微见澜 Ripplesight”，统一文档导航、浏览器标题、首页、PRD、根目录说明与 AI 导出中的项目称呼。保留真实技术路径和标识，以及既有验证历史；需求、范围和业务实现未改变。

`pnpm index`、`pnpm check`（19 项现有测试及 TypeScript）、`pnpm build`、`pnpm verify` 均通过。另对 34 个生成页面检查：HTTP 200、无 footer 元素、正式名称存在、旧页脚品牌不存在。实际浏览器刷新后正式名称显示正确，footer 元素数量为 0；默认视口内容宽度与滚动宽度均为 831px，390px 窄屏覆盖下两者均为 375px（扣除滚动条），无整页横向溢出。检查后恢复默认视口；页面末尾保留文章导航与原文入口，没有全局页脚。

本机截图：`.tools/requirements-workspace/2026-10-07-footer-cleanup.jpg`、`.tools/requirements-workspace/2026-10-07-brand-mobile.jpg`。未新增测试、未提交、推送或对外部署。

## 2026-10-07 Ripplesight 仓库与项目改名

本人明确要求将 GitHub 仓库和当前项目名称统一为 `Ripplesight`。已通过 GitHub API 将 `StephenQiu30/hotkey-server` 改为 `StephenQiu30/Ripplesight`，仓库 ID 仍为 `1217852212`，默认分支仍为 main；description 同步当前产品定位。本机 origin 更新为 `https://github.com/StephenQiu30/Ripplesight.git`，`git ls-remote origin HEAD` 验证成功，远端 HEAD 仍为 `5e098e867543a7764891946eb93e5965d934c8a5`。

当前源码同步产品标识、网页和 PWA 元数据、登录邮件及通知、报告与公开分发的品牌、MCP serverInfo、CLI 说明、采集 User-Agent、下载文件名前缀、根文档与 workspace 链接。包名为 `ripplesight-backend`、`ripplesight-frontend`、`ripplesight-docs`；镜像默认使用 `ripplesight-` 前缀。`uv lock --offline` 只更新并重排根虚拟包，依赖版本未变。文档 basePath、canonical、导航、raw、AI 导出与验证脚本使用 `/Ripplesight`。

兼容边界：保留 `HOTKEY_*` 环境变量、数据库和数据卷、Compose 已有项目名、登录 Cookie/HTTP 协议、MCP 工具名、生成客户端类型名以及 Obsidian 默认 `HotKey/` 导出目录。本机共享 checkout 与既有 worktree 路径未移动；被冻结的 Flutter 项目未改动。未改业务能力、权限、数据库结构或自动化任务。

| 检查 | 结果 |
|---|---|
| backend Ruff、格式、mypy | 全部通过；435 个源码文件类型检查通过 |
| backend unit + architecture | 最终全量复测 1585 通过；首次 1584 通过、1 项 MediaCrawler 进程终止测试发生 OS `PermissionError`，该项单独复测通过后全量复测也通过；未修改采集进程逻辑 |
| frontend lint、typecheck、format、test、build | 全部通过；118 个测试文件、939 个测试通过 |
| workspace index、check、build、verify | 全部通过；34 页、19 个工具测试、TypeScript、逐页 HTTP/原文与 AI 导出有效；舆情/评论/情感查询分别命中 13/16/10 条 |
| 文档静态产物复核 | 34 页无 footer、旧 Pages 路径、旧仓库链接和旧中文品牌 |
| Compose 配置及 Git 差异 | `docker compose config --quiet`、`git diff --check` 通过；未重启既有 8666/8667 服务 |
| 本机浏览器 | 文档桌面与 390px 预览无整页横向溢出；文档标题、导航、canonical 和原文指向新名称，footer 数量为 0；手机菜单与 Ripplesight 搜索可用；8686 临时应用预览的首页和关于页显示新品牌 |

截图保存于本机忽略目录 `.tools/requirements-workspace/`：`2026-10-07-ripplesight-docs.jpg`、`2026-10-07-ripplesight-docs-mobile.jpg`、`2026-10-07-ripplesight-app-mobile.jpg`。测试后恢复默认视口；本机文档阅读入口为 <http://127.0.0.1:8668/Ripplesight/>。

待发布：GitHub Pages API 已报告新地址 <https://stephenqiu30.github.io/Ripplesight/>，但其当前 HTML 仍为旧构建，标题为 `HotKey 文档 · HotKey 文档`，样式资源 `/hotkey-server/_next/static/css/11c59cc40cabfed8.css` 返回 404。GitHub 官方说明仓库改名不重定向项目站点地址（[来源](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)）。需提交、推送并完成 workspace-site 部署后再验线上；本轮尚未获得 AGENTS §7 所要求的明确提交/推送授权，源码与既有 workspace 调整保留为未提交修改。本机验证不代替线上部署、数据库集成、真实采集或模型验收。

## 2026-10-07 父工作区、客户端与描述补齐

按本人补充要求，将实际父目录迁为 `/Users/stephenqiu/Desktop/StephenQiu/Ripplesight`，实际仓库目录为 `ripplesight-server/` 与 `ripplesight-app/`。迁移前后分别核对两个仓库的 Git diff 与未跟踪文件 hash，一致；所有既有修改原样保留。旧父目录和旧仓库名仅保留符号链接，供未迁移的会话访问。外部 worktree 的 `.git` 指针和主仓库登记路径改为新地址；已有缺失的 deploy worktree 仍标记 prunable，未清理或改变其状态。

Python 虚拟环境的 36 个启动/激活文件迁到新绝对路径，prompt 使用新包名。新路径执行锁文件同步后恢复了原有额外安装的 `tenacity==9.1.4`；未增加项目依赖。父目录新增 README/AGENTS 作为人和 AI 的入口；Claude 已有设计预览配置仅改显示名，保留真实的临时文件来源路径。

冻结客户端 GitHub 仓库由 `hotkey-app` 改为 [Ripplesight-app](https://github.com/StephenQiu30/Ripplesight-app)，ID 仍为 `1247949203`，main HEAD 为 `6697bd9fc71891e4f29510329e5c3408d1745284`，本机 origin 同步。纠正其旧 About 对“内容创作者 Web 工作台”的错误描述，明确“Flutter 客户端预留仓库；当前冻结，仅维护工程约定，尚无可运行应用”。App README、规范和 GitHub 模板使用新品牌与链接；未初始化 Flutter 工程。

主仓库 GitHub About、README、Web 标题与 description、PWA 描述、关于页、三个包与需求文档站描述统一当前定位：个人非商业使用的公开资讯阅读与舆情监控项目，围绕关键词连接来源材料、讨论与事件进展。关于页纠正首页用途为公开资讯阅读；描述不承诺已经完成真实业务验收。

新路径下 frontend 的 lint/typecheck/format、939 个测试及构建通过；backend Ruff/格式、435 源码的 mypy 与 76 个配置/提示词测试通过；workspace 的 19 个测试、TypeScript、34 页构建、HTTP/原文/AI 导出与搜索检查通过；App 公共文档和模板检查、两仓库 `git diff --check` 通过。已有 8666/8667 服务没有重启；文档预览使用新目录启动。

未完成的应用设置项：Codex `list_projects` 仍返回项目标签 `HotKey` 与旧路径，没有自动迁移。自动审批拒绝通过 `com.openai.codex` 界面改项目设置，理由是应用安全限制；当前没有可用的专用项目改名工具，未绕过限制编辑应用内部状态。需在 Codex 中将保存的项目目录切换为新父目录；兼容链接保证现有聊天仍能访问文件。源码尚未获明确提交/推送授权，GitHub README、Pages 与正式运行版本仍待发布。

浏览器复核补充：新目录 8686 临时预览的首页标题为 `Ripplesight · 公开资讯阅读与个人舆情监控`，PWA name/short_name 均为 Ripplesight，description 为当前项目定位；关于页的标题、品牌与正文说明正确。默认 1280px 与 390px 视口无整页横向溢出，测试后恢复默认视口并关闭临时应用预览；截图为 `.tools/requirements-workspace/2026-10-07-ripplesight-description.jpg`。新目录的 8668 文档预览继续保留。

## 2026-10-07 授权提交与推送

本人随后明确要求“将代码提交到main并推送”。两个仓库提交前均在 main，与各自 origin/main 一致；本轮待提交内容均为上述 workspace、品牌、目录关联与描述调整，未包含本机凭据、截图或构建产物。锁文件中的 87 项依赖名称及版本与改名前一致；提交前 workspace 的 19 项测试、TypeScript、34 页文档校验和 App 公共文档/模板校验再次通过。

- 主仓库 [002c6206](https://github.com/StephenQiu30/Ripplesight/commit/002c620657fb4573e9374a7451b0677b0f49b6ca)：统一 Ripplesight 命名与需求工作区入口，已推送 main。
- 冻结 App [b9447bf](https://github.com/StephenQiu30/Ripplesight-app/commit/b9447bf159a25700995cbf84648bfbe122128194)：统一客户端命名与说明，已推送 main；[远端文档 CI](https://github.com/StephenQiu30/Ripplesight-app/actions/runs/37564613455) 成功。
- 推送后 git ls-remote 确认两个远端 main 与对应本机提交一致；主仓库 [Workspace site](https://github.com/StephenQiu30/Ripplesight/actions/runs/37564606103) 构建与部署成功。该提交的 backend/frontend/contract/runtime 工作流在此记录时仍运行中，不将本机结果代替远端结果。
- 线上 <https://stephenqiu30.github.io/Ripplesight/> 返回 200，标题为 `Ripplesight 需求 workspace · Ripplesight 文档`；两份样式资源均返回 200，HTML 不再引用旧 `/hotkey-server/_next/` 路径，且无全局 footer。此前仓库改名导致的旧资源 404 已由新构建修复。
- 更新提交状态后，workspace check、build 通过；首次 verify 因 8668 预览进程未运行而失败，重新启动已有预览后复验通过：34 页正文/原文与 AI 导出有效，舆情/评论/情感搜索命中分别为 13/16/10 条。未改验证脚本。
- Codex 项目清单现已有 Ripplesight，路径为新父目录；旧 HotKey 项目仍保留。此前界面安全限制是历史记录，不再阻碍从新目录工作。

本次授权用于提交、推送及其既有 CI 流程；没有重启或重新部署本机 8666/8667 业务服务，没有选择或执行业务 POC。父目录 README/AGENTS 属于两个仓库之外的本机入口，未据此建立第三个 Git 仓库。

## 2026-10-07 PM 调研与国内平台 POC 需求整理

范围：按用户要求使用 PM 技能，整理关键词帖子与评论监控、相关性/相似度及时效性；最终国内主流与 X/Instagram 等海外覆盖，本次 POC 验证方向是国内。当前交付为需求与调研文档，没有执行业务代码实现、平台采集、模型分析、采购或访谈；没有提交、推送或发布。

使用的技能：`pm-market-research` 的 competitor-analysis、market-segments、customer-journey-map；`pm-execution` 的 create-prd、test-scenarios；`pm-product-discovery` 的 identify-assumptions-existing、prioritize-features。商业对标为识微、蚁坊、清博 AiPin、Meltwater、Brandwatch；开源方案为 MediaCrawler、TrendRadar、BettaFish、RSSHub。官方资料链接随相应判断保存，厂商声明、源码事实、AI 提案和未知项分开。

产物：更新[总 PRD](product/prd/01-PRD.md)、[需求入口](product/reference/04-需求与验证入口.md)、[源码差距与验证设计](research/2026-10-07-热点事件需求核对.md)；新增[市场竞品调研](research/2026-10-07-热点监控市场与竞品调研.md)、[用户细分旅程与优先级](research/2026-10-07-用户细分旅程与POC优先级.md)、[国内 POC 卡](research/2026-10-07-国内平台关键词监控POC验证.md)。同步首页、术语、README、阅读清单和 BACKLOG，进度仍只在 BACKLOG。没有新建第二份产品需求源。

| 检查 | 实际结果与边界 |
|---|---|
| `pnpm index` | 最终执行无改动，37 页索引已是最新 |
| `pnpm check` | 退出 0；元数据、路径、锚点、编号和长度有效，19 个既有测试与 TypeScript 通过 |
| `pnpm build` | 退出 0；37 页正文、原文、AI 导出及中文 Pagefind 索引，3075 个词 |
| `PORT=18668 pnpm preview` | 本轮静态预览仅监听 127.0.0.1:18668；使用既有脚本，保留便于阅读 |
| `DOCS_PREVIEW_URL=http://127.0.0.1:18668/Ripplesight pnpm verify` | 退出 0；37 页与原文 HTTP/导航/嵌入/链接/AI 导出通过；舆情、评论、情感搜索分别 14/20/13 条 |
| 实际浏览器 | 首页显示已确认国内 POC 方向；搜索“竞品”出现新调研，点击打开对应页面，标题、五家对标、官方来源和分析链接可读；最终构建后刷新确认最新文字 |
| 文档复核 | 独立只读核对商业资料与范围；修正旧竞品高低评分、绝对覆盖承诺、后续日报/情感与当前 POC 混写；未把样本门槛当成质量评测通过 |
| `git diff --check` | 通过；本轮文档未提交、未推送 |

检查基于 `751a5168` 之后的共享工作目录。过程中出现非本次任务的部署修改，包括根 PROJECT/README、Compose、示例配置、runtime 工作流及 workspace Docker/Nginx 文件；均保留，没有据此认领部署结果。8668 已由并行 Docker 服务占用，因此本轮用独立 18668 检查静态阅读，不重启或重建其服务。构建中的根文件指针会包含当前共享文档，不能把整个工作目录归为本次成果。

上述结果仅证明文档可读、可检索和证据关联有效，不证明真实平台、海外接入、模型增益、评论代表性或持续运行通过。平台穷尽清单、首平台、运行输入和指标仍按 POC 卡核对；AI 细分和情绪假设尚无用户研究验证。

## 2026-10-07 Docker 部署与命名统一

按本人要求将前端、后端和现有知识库阅读预览统一由 Docker 运行，并将 Compose 本机项目名从 `hotkey` 改为 `ripplesight`，生产配置名改为 `ripplesight-prod`，CI 项目名同步使用新前缀。当前容器为 `ripplesight-backend-1`、`ripplesight-frontend-1`、`ripplesight-workspace-1`，分别使用同名 `ripplesight-*:local` 镜像，网络为 `ripplesight_default`。后端容器用户为 `ripplesight`，UID 仍为 10001。

执行 `docker compose --env-file .env -f docker-compose.yml build backend frontend workspace`，成功构建后用显式 `--project-name hotkey` 停止并移除旧应用项目，再以新项目执行 `up --detach --no-build --wait --wait-timeout 120 backend frontend workspace`。切换前确认旧项目只有三个本仓库应用容器且没有持久数据挂载；前后环境配置摘要一致，未执行数据卷删除、环境栈启动或数据库初始化。可选环境栈支持显式指定已有 PostgreSQL、Redis、Kafka 卷名，复用检查通过。

实际结果：三个新容器均为 healthy，旧应用容器和 `hotkey_default` 已移除；8666 首页、登录、API 代理，8667 就绪接口与 Swagger，8668 知识库均返回 200。知识库 Docker 构建中的 `pnpm build`、`pnpm check` 通过，19 项既有测试和 TypeScript 通过；部署后 `pnpm verify` 验证 37 页正文与原文、导航、嵌入、链接和 AI 导出，舆情/评论/情感检索分别命中 14/20/13 条。知识库跳转保持宿主端口、Markdown MIME 与缺失/未发布路径 404 已验证。Compose 开发/生产定义一致性、生产凭据隔离、项目命名和数据卷复用配置检查通过；生产配置仅用示例配置解析，没有生产部署。

本轮为部署与命名维护，保留并行需求文档；没有执行平台业务采集或模型验收，没有提交或推送。业务 POC 的状态仍以 BACKLOG 和验证卡为准。

## 2026-10-07 GitHub 免费取数专项调研

按用户最新指令，将方案研究重心切换到 GitHub 热点、关键词帖子与评论项目，并把“无必需付费取数 API/服务”置于 star 之前。沿用 pm-market-research 的 competitor-analysis，以及此前已应用的假设识别、优先级与验证场景方法；通过用户指定 GitHub 插件核验 15 个主要候选及 2 个国内覆盖缺口排除样本的元数据、许可和关键源码。固定提交与原始元数据入口保存在[专项报告](research/2026-10-07-GitHub免费热点与评论采集调研.md)，没有安装上游软件、登录平台或实采。

新增专项报告；同步需求入口、总 PRD、首页、POC 卡、术语、阅读清单、workspace README 及 BACKLOG。旧开源研究和商业对照新增当前入口，保留历史原文；开源决策仅补关联证据，未改决策。明确 MediaCrawler 自定义许可、BettaFish 混合许可、Spider_XHS 缺失 LICENSE、热榜时间语义、公共免费实例依赖，以及公众号/视频号/头条的链路缺口。独立复核四个热榜/RSS 项目的元数据和费用结论，并将 RSSHub 未核验范围改为“本轮未证明”，没有写成否定事实。

| 检查 | 结果 |
|---|---|
| `pnpm index` | 38 页索引已更新；最终再执行无差异 |
| `pnpm check` | 退出 0；文档元数据、命名、关联、锚点、正文长度有效；当前共享目录 25 项测试及 TypeScript 通过 |
| `pnpm build` | 退出 0；修正文案后重建通过，38 页正文/原文/AI 导出，Pagefind 3335 个词 |
| `DOCS_PREVIEW_URL=http://127.0.0.1:18668/Ripplesight pnpm verify` | 退出 0；38 页 HTTP 与原文一致，导航、链接和 AI 导出有效；舆情/评论/情感检索分别 15/22/13 条 |
| 实际浏览器 | 首页显示 GitHub 优先入口；搜索 WeiboSpider 出现报告章节，点击打开，star 表、免费门槛、国内矩阵和未实测状态可见；重建后刷新确认最终 RSSHub 边界文案，保留报告阅读标签 |
| `git diff --check` | 通过；未提交、未推送 |

检查使用当前共享目录和本轮独立 18668 静态预览。并行任务继续修改 Docker、开发预览/热更新脚本和相关测试，本轮不修改或认领这些实现，也未重启业务或 Docker 服务；25 项是执行时的共享测试集合，不是本轮新增测试。以上仅证明调研已归档、文档可读可检索；不证明取数已免费跑通、完整平台覆盖、评论完整性、相关性增益或实时 SLA。

## 2026-10-07 本机 Docker 热更新

本人明确要求代码和知识库文档修改后自动生效。本机默认加载 `docker-compose.override.yml`：`ripplesight-backend` 只读挂载 API 源码并使用 Uvicorn 重载；`ripplesight-frontend` 使用 Next.js 开发镜像与只读源码挂载；`ripplesight-workspace` 在容器内监听只读作者来源，筛选文件、捕获来源副本，执行现有文档校验、静态构建、Pagefind 与 AI 原文导出后整体切换预览版本，并通过浏览器事件连接刷新页面。失败保留上一版；构建期间的新修改在下一轮处理。依赖和生成物不回写宿主机，数据库、账号与内部知识库发布流程没有调整。可选服务的容器名也统一为 `<Compose项目名>-<服务名>`，不再使用数字后缀。

实际热更新检查：

- 临时修改前端关于页标题，在已打开的浏览器中自动显示新标题，无手动刷新、镜像重建或容器重启；移除标记后再次自动恢复原标题。
- 临时在 API 已加载模块中增加固定验证输出，WatchFiles 自动重载并执行该输出，随后 `/api/ready` 返回 200。前后端验证标记移除后，源文件 SHA-256 与验证前一致。
- 在已登记的术语表追加明确的临时验证标记，约 46.1 秒后 HTML、raw Markdown 与 `llms-full.txt` 全部出现修改；已打开的浏览器自动刷新。实际 Pagefind 索引返回 1 条术语表命中，浏览器搜索也展示新增片段。验证后仅移除本次追加内容，作者文件 SHA-256 与追加前一致。
- 前端 lint、TypeScript、Prettier、939 项测试及生产构建通过。workspace 校验、25 项测试（新增 6 项覆盖来源筛选、越界拒绝、失败回退、构建中并行编辑、搜索产物完整性、预览 MIME/路径与浏览器刷新通知）、TypeScript 与 38 页静态构建通过。基础与生产 Compose 一致性、生产凭据隔离检查通过；显式基础/生产配置无开发挂载、development 构建目标或重载参数。

首次非 root 启动发现运行包管理器会尝试重装依赖，已修为直接使用镜像内锁定的工具；文档构建仍执行 `package.json` 中现有 build 脚本。初期并行编辑会使构建被丢弃的问题也已修正：发布完整来源副本的构建，随后处理新修改，保持预览可用。生产与 CI 显式选择既有 Compose 文件，未部署生产；未提交或推送。本记录只证明本机开发热更新，不代表真实采集、模型分析或业务 POC 验收通过。

末次全量 `pnpm verify` 未通过：运行中的上一有效版本与正在并行改写的 PRD 原文不同。自动构建日志随后报告缺失的 `product/reference/07-关键词监控数据库设计.md` 引用，以及尚未更新的首页索引；这些共享文档不属于本次热更新配置修改，未覆盖或代写。新来源暂未发布，三个容器仍 healthy，当前有效版本的前端、API 代理、就绪接口及知识库首页均为 HTTP 200。监听继续运行，引用补齐、执行索引生成并通过校验后会自动切换；不能将先前 38 页构建通过当作这些正在编辑的文档已经验证通过。

## 2026-10-07 pm-execution 需求与工程设计优化

按用户要求，以既有 GitHub 免费项目研究为输入，使用 `pm-execution` 的 create-prd、prioritization-frameworks、outcome-roadmap、pre-mortem、test-scenarios 整理全链路设计。保留总 PRD 为唯一需求原文、PROJECT 为架构原文、BACKLOG 为唯一进度来源；没有在父目录或 App 仓库另建需求体系。

交付及职责：

- [总 PRD](product/prd/01-PRD.md)：12 项功能条款及 MoSCoW 优先级、12 项非功能条款；说明费用、正确性、时效、性能、访问隔离、恢复、维护和可解释性的验收口径，数值初值仍标为提案。
- [PROJECT §12](../PROJECT.md#12-关键词监控工程设计提案)：开源项目采用边界、现有领域职责、数据流程、任务状态、共享预算、错误分类与 API 演进。
- [数据库设计](product/reference/07-关键词监控数据库设计.md)：只读核对 schema/ORM/服务，列现有表、字段、唯一键、FK、索引和删除语义；提议新增有界候选关联，补四档相关性、时间和父链契约，以及查询、留存、恢复与迁移方案。
- [验证与交付设计](research/2026-10-07-关键词监控验证与交付设计.md)：7 个结果阶段、工作量/容量假设、需求到设计追踪、21 项验收场景、三类风险及关口。未派发实现，因此以设计提案归档，没有将新计划假标为生效。

同步了需求入口、索引、阅读清单、术语、三个关联能力、POC 卡与历史核对文档。独立复核修正：相关性不得强制产生情感；B 站桥接重读旧 JSONL 不等于实采；缺直接父 ID 不等于一级评论；暂停与取消分开；来源成功为空和候选被全部排除分别计数；页检查点不等于完整覆盖水位；查询分片和子任务不得放大预算。最后补齐固定结果 manifest 的分页绑定、本轮查询/观测一致性和原抓取批次/缓存读取的时间证据。

| 检查 | 实际结果与边界 |
|---|---|
| `pnpm index` | 40 页索引已更新；最终执行无改动 |
| `pnpm check` | 退出 0；元数据、命名、链接、锚点、正文长度有效；当前共享目录的 25 项测试与 TypeScript 通过 |
| `pnpm build` | 最后复核修改后退出 0；40 页正文/原文/AI 导出有效，Pagefind 索引 3875 个词 |
| 18668 静态预览 `pnpm verify` | 最终退出 0；40 页 HTTP、原文、导航、嵌入、改写链接与 AI 导出有效；舆情/评论/情感搜索命中 16/25/15 条 |
| 实际浏览器 | 首页显示当前工程设计；搜索“数据库”可打开新设计，PRD 功能/非功能条款及交付阶段/追踪/风险可读；最终重载确认错挂候选场景、抓取批次与不可变结果清单文字 |
| 8668 既有 Docker 阅读入口 | 构建切换期间曾遇旧有效快照原文差异；自动切换后最终 verify 退出 0，40 页原文/导出及搜索 16/25/15 条全部通过；本轮未重启或重建该服务 |
| `git diff --check` | 通过，未提交、未推送 |

本轮没有修改 DDL、ORM、API、业务实现或冻结 App；没有连接数据库、执行采集/模型、做性能实测或改变部署。源码事实、设计建议、文档检查与业务可用性分开记录，不能由上述结果推导免费链路、全平台覆盖、相关性质量或实时 SLA 已达标。并行任务的 Docker、预览/热更新与测试改动完整保留；25 项测试是共享目录现有集合，本轮未新增业务测试。文档保持未提交、未推送。

## 2026-10-07 Chrome 关键词 demo

新增本机免费 B 站采集 demo、持久化小时调度检查及运行说明；业务证据见 [首轮记录](records/2026-10-07-Chrome关键词demo验收.md)。workspace check/build 通过（25 项测试，42 页 Pagefind 与原文导出），元数据和新增公开资料清单已同步。后台本机预览继续使用 8668；业务 demo 为仅 loopback 的 8669。真实数据、Cookie 和截图不进入公开文档产物。

后端 Ruff、format、mypy 与 1593 项 unit/architecture 测试通过。全套测试首轮因未设置普通 Settings 的测试 URL 中断；改为两个 DB 环境变量均指向独立库后，maxfail=1 停在既有 `test_coverage_http_keeps_analysis_anomaly_separate_from_unknown`，253 通过、13 跳过、1 失败。未将失败或跳过计作通过，测试库均已删除。手动首轮与一次短间隔定时实采成功（累计 4 帖/1 评论），最新用户的核心验收通过；完整 POC 卡仍有待验证项，理由在业务记录中列明。

浏览器补验：沿站内实际 `/Ripplesight/research/…/` 链接打开运行说明成功；搜索 `Chrome` 命中首轮验收与运行说明。业务 demo 8669 桌面与 390px 阅读通过，结果页保留为可操作输出。


## Chrome 工作台接入与注册流程（2026-10-07）

本轮新增工作台接入、注册修复两份验收记录，并更新 BACKLOG、PROJECT、PRD 与运行说明。文档检查 25 项通过；首次构建发现新记录漏登公开清单，补齐后重新构建通过，44 页正文、原文与 Pagefind 索引生成。业务证据见对应记录，文档构建不代替真实采集或登录验收。未提交、未推送。


## 2026-10-08 全站页面需求与工程设计

按本人要求，先将现有 Figma 重建与监控工作台代码以 `4489b400` 推送 main，再使用 pm-execution 的 create-prd、user-stories、test-scenarios 方法整理需求。新增[专项 PRD](product/prd/03-PRD-全站页面需求.md)、52份单页功能表与6份接口/数据库/非功能/验收/现状字典，共59份文档；同步总PRD、需求入口、历史计划边界、PROJECT与BACKLOG。原始源仍在 docs，进度仍只在 BACKLOG。

| 检查 | 结果与范围 |
|---|---|
| 源码覆盖盘点 | 52/52 page.tsx 路由对应唯一需求页，共185项主要行为；247/247生成函数有方法/路径/类型/路由引用；123/123 CREATE TABLE有字段与现有约束字典。没有查询业务库来推断运行结构。 |
| `pnpm index` | 通过；新增页面需求导航分组，首页生成索引包含全部文档。 |
| `pnpm check` | 最终通过；106页元数据、命名、编号、长度、链接和锚点有效，25项工具测试及TypeScript通过；导航回归检查首尾页面入口。 |
| `pnpm build` | 最终通过；106页正文、raw、llms与Pagefind中文索引，5915词；采用单个静态生成worker。 |
| `pnpm verify` | 退出0；106页HTTP正文/原文、导航、元数据、根文件嵌入、链接与AI导出通过；舆情17条、评论39条、情感26条搜索结果，首条可打开。 |
| 实际浏览器 | 8668从新总PRD页面总表进入“今日热点”；功能表、方法路径、权限和验收正文可读。搜索“监控主题”后选择“监控主题工作区”，准确到达新增需求页并显示草稿/页签/过期结果要求。 |
| 差异与边界 | `git diff --check`通过；代码归档之后未改frontend或backend业务代码、schema、API生成物，未重新声称前端全量或业务验收通过。 |

修复过程：初次检查发现总PRD超过正文上限22字符、新专项草稿不能进入公开清单；精简新增入口文字，并按用户已确认的整理范围设为生效文档，正文显式保留增量与阈值为未确认提案，没有放宽校验。新增导航断言先因尾斜杠、Agent文件名空格不匹配失败，按实际路由修正后25项全部通过。

本机4worker构建成功，但Docker文档容器在2GB上限内构建被终止（137），并遗留构建子进程。限制知识库静态生成为1worker，仅重启知识库容器清理残留后，106页、搜索和AI原文已原子切换完成，容器恢复健康；前后端服务未重启。此处是文档容量修复，不增加业务功能或放宽资源上限。

仅验证文档持久化、阅读、检索、静态盘点与工具行为。新增云收藏/关注、公开分析/趋势、运行批次和告警已读均未实现；性能数字、样本阈值与留存是提案。没有执行真实采集、模型调用、通知、数据库迁移/恢复，也未完成Claude或用户体验审查。后续业务验收按独立场景记录。

## 2026-10-08 从当前页面收敛需求、修复水合告警

用户进一步明确：从前端实际展示字段、数量与操作反推需求、数据库和接口，替换历史冗余；不能以文档/接口/表数量作为需求成立或交付完成的依据。使用 pm-execution 的 create-prd、user-stories，原位改写页面需求、总纲、接口/数据设计、非功能与验收；没有另建产品体系。

本轮以开始时 `67df5ab1` 的页面、实际调用组件、生成类型、后端路由和唯一 schema 为事实依据。每页注明字段、当前读取数量、用户动作、持久化位置、接口、存储依赖和取舍；区分主流程、既有辅助入口、冻结兼容。撤销未实施的云收藏/关注、阅读账本、独立运行批次、情感快照、告警已读以及预设大容量门槛。保留内容版本/观察/评论关系、任务恢复、许可、后台消费者需要的存储；没有业务 DDL 或数据迁移。旧前端计划标记废弃，总 PRD、PROJECT、入口、工程说明和本机运行文档同步。

报错在原 Chrome 标签复现：`<html>` 多出 `data-immersive-translate-page-theme="light"`，同 URL 服务端 HTML 不含该属性，来源是翻译扩展在 React 接管前修改 DOM。参考 [Next.js 水合说明](https://nextjs.org/docs/messages/react-hydration-error)与 [React hydrateRoot](https://react.dev/reference/react-dom/client/hydrateRoot)，仅根 DocumentRoot 使用单层 `suppressHydrationWarning`，不关闭 SSR 或过滤控制台。新回归先失败再通过，证明根属性差异不再告警，同时真实后代正文差异仍进入恢复错误。另删除唯一使用方未传入的 PageContainer header 插槽和旧固定页头分支，保留正文滚动及登录页脚。

文档可读性修复：内部允许清单补齐当前页面需求及依赖，不改变任何账号权限；只读构建仓库快照验证跳转。浏览器发现 Codex/Agent 带空格文件名被渲染成普通文字，修正总表和索引生成器；新增回归覆盖每个页面从总表及首页进入内部阅读链接，修复前在 Codex 链接失败，修复后通过。数据库摘要采用 SQL 顶层列声明，避免将多行 CHECK 中的同名字段条件误当类型；完整约束仍以唯一 schema 和现状字典查证。

| 检查 | 实际结果与范围 |
|---|---|
| Git 起点 | main 与 origin/main 均为 67df5ab1、工作区干净；fetch 后无分叉；首次 push 为 Everything up-to-date，无空提交 |
| Web 工程 | lint、typecheck、format:check、973 项测试和生产 build 全部退出 0；末次 README 修改后格式检查再次通过 |
| 根水合回归 | 两项分别验证扩展根属性兼容与后代真实 mismatch；与现有语义组件回归合跑通过 |
| 文档工程 | index、check（26 项测试及 TypeScript）和 build 退出 0；页面、原文、AI 导出及 Pagefind 产物齐全 |
| 8668 预览 | pnpm verify 退出 0，检查公开页面与作者原文、导航、嵌入、链接、AI 导出；“舆情/评论/情感”分别命中16/38/25条。编辑期间曾因新建主题原文尚未切换失败，热更新完成后重跑通过 |
| 实际文档浏览 | 总表打开收藏需求并可见本机存储/读取数量；修复后三个空格文件名呈现链接，点击 Codex 公告日历可读单页字段；搜索“取舍标准”进入收敛方案对应章节 |
| 实际登录浏览 | 原 Chrome 刷新后已是登录用户首页，未代为退出。独立匿名页测试 1440×1000 与390×844，DOM宽度和横向范围一致；登录方式初始加载、正常表单、空表单提示、方向键/Enter切换、访问/topics回到带安全returnTo的/login均可见；错误/警告控制台为空；临时视口已恢复 |
| 本机证据 | `.tools/service-doc-audit/` 保存 Web 测试/构建日志及登录截图；`.tools/page-driven/` 保存源码核对资料、最终文档检查/构建/verify和复审结果（均不提交） |
| 独立审查 | 按 AGENTS 尝试只读 Claude CLI 复审，返回 Login expired，退出1；没有获得审查结论。按工程定义不能标记“代码完成”或“能力可用” |
| 服务与数据边界 | 本机 backend/frontend/workspace 容器健康；本轮没有重启业务服务、实采、模型调用、通知外发、登录凭据修改、业务库写入或生产部署 |

正式内部知识库仍未启用：未发现 `.tools/workspace/config.json`，当前 Docker API 无有效 WORKSPACE 配置。公开静态预览可读、仓库内部快照回归通过，都不能证明真实账号的内部阅读/编辑/Obsidian发布已验收。LOCAL 明确已有独立副本的更新/合并方式，不能重初始化覆盖草稿。未重验全站五状态、数据库实际恢复、真实来源/邮件/送达、长期运行或生产容量。提交与推送结果以本记录所属 Git 提交及交付回复为准，不在此预造提交哈希。

## 2026-10-08 按原稿重新实现基础布局与核心页面

用户明确否定旧前端本身作为设计依据。本轮从 main 的 `3cf987f5` 干净工作区开始，以此前从 Figma 桌面端导出的10页原稿为视觉依据，重新实现固定302px侧栏、正文留白、语义排版、8类核心页面及共用状态。原有外观被替换，接口、权限、内容许可和数据版本合同继续核查。使用 shadcn、Vercel React Best Practices 与 pm-execution 的 create-prd/test-scenarios 方法；未创建另一套需求目录。

页面变化包括：今日热点仅展示事件序列；探索使用类型/时间/排序及平台筛选；事件按照事实、趋势、时间线、来源与情感辅栏组织；日报使用专用正文比例和紧凑元数据；模型榜使用排名表；监控默认为关键词、观测、平台、规则及告警的连续详情，另设真实结果和设置入口；收藏支持本机备注、排序与选择导出；登录按原稿双栏与四项页脚重新排列。收藏备注进入本机持久化并随Markdown导出；旧JSON备份合同不含备注，不承诺云同步。

需求原位修正：8个核心页面分别列字段、数量、操作、当前合同和存储决定；两个旧监控入口指向同一工作区定义。接口设计补充最小聚合/搜索/关注/已读提案，数据库优先复用现有事实、观察、评论、告警和版本关系；未执行DDL，也不将设计提案当作已存在接口。旧大卡片改版计划退出当前派发。

| 检查 | 实际结果与边界 |
|---|---|
| Web工程 | lint、typecheck、format:check、124个测试文件970项测试、生产build全部退出0。包含新增备注持久化/损坏保护/删除后拒绝写入/长度限制和首页403状态回归；既有版本、许可、草稿与运行状态测试保留。 |
| 文档工程 | index、check（26项工具测试及TypeScript）及build通过；107页正文、原文和Pagefind索引生成。记录更新后的复验结果随本提交保存，不用文档通过代替业务通过。 |
| 桌面及窄屏 | 首页、探索、事件详情、固定日报、模型榜、收藏、登录、监控的1440px和390px正常布局均浏览核对；窄屏无横向溢出。原稿与截图保存在本机`.tools/figma-shadcn-review/`，不将固定样本或截图打包进业务页面。 |
| 状态与交互 | 首页正常/空/加载/503错误/403无权限在两种宽度观察；空统计使用“—”。筛选器Space打开、Escape退出和焦点返回，匿名监控回跳登录，收藏备注保存并刷新保持通过。尚未完成每个路由的全部五状态浏览器矩阵。 |
| 生产模式 | 独立8766/8767固定样本环境运行同一生产构建；首页布局和无警告/错误控制台已核对，日报与榜单复核截图。内置浏览器出现过标签失效、导航network error及收藏读取timeout，刷新后榜单正常。用桌面Chrome交叉检查：探索→收藏、加入两条样本、最近/最早排序及URL同步、首页→事件详情与4条事实/来源均正常；未复现内置预览异常，不能据此声称已修复其根因。 |
| 真实监控 | 用户已有Chrome会话的8666主题工作区可读取既有主题和5条帖子/评论；只读进入结果，未新增采集、修改配置、退出登录或改动凭据。 |
| 审查 | Claude CLI再次返回Login expired，退出1；没有审查意见，不能按AGENTS§6认定“代码完成”或“能力可用”。 |
| 未验证范围 | 原稿最终逐像素用户评审、公开统计/情感/曲线/趋势与搜索等新合同、完整真实登录和来源/通知/长期运行验收均未完成；未修改后端schema或生成API、未迁移业务数据、未动冻结App。 |

临时验收服务与本机截图仅用于本轮检查，既有Docker服务保持运行。Git提交和远端同步以本记录所属提交及交付回复为准。后续进度仍只记BACKLOG，不据历史完成项认定本次原稿验收完成。


## 2026-10-08 侧栏宽度与手动调整

官方Sidebar/Resizable专项：HEAD加本次侧栏文件的隔离生产快照通过Web lint/typecheck/format:check、125文件1031测试和build；1440/390正常、空、加载、错误、无权限10状态及拖动224–320、240默认、48折叠、双击恢复、刷新/断点恢复与输入快捷键已核对。独立只读subagent复核通过，生产CSP保持严格限制。详细证据见[侧栏验收](records/2026-10-08-侧栏宽度与手动调整验收.md)。

共享目录在并行workspace→docs迁移时的末次typecheck/build失败于editor/content.ts及已删除文档路由；旧workspace校验失败、新scripts/docs校验当时存在32条迁移引用。保留这些并行改动；隔离通过不等于当前整个工作区通过，未提交推送。

末次文档索引和scripts/docs检查通过：115份文档。并行迁移后续恢复了editor/content.ts；末次共享Web build/typecheck/lint/format:check全部通过，122文件1019项测试通过（现存用例零跳过/零失败）。下降的用例数量来自并行文档编辑器测试删除。未提交推送，后端不在本次侧栏检查范围。


## docs 与 Obsidian 文件管理迁移（2026-10-08）

在线项目知识库退役，当前原文在 docs，工具仅运行 scripts/docs 的 index/check。迁移、完整性、独立审查及各项检查证据见 [迁移记录](records/2026-10-08-docs与Obsidian文档管理迁移.md)。Web1019项与生产build通过；后端普通pytest1623通过、958环境跳过，契约无漂移。个人Obsidian状态被忽略，业务导出保留。当前未提交推送，远端历史Pages仍保留，实际Obsidian操作待验收。

## 2026-10-08 监控工作区GSAP过渡

基础交互已按本人要求提交推送main（0a9e18b7），继续实现监控结果／运行／编辑及进阶／报告设置的可中断过渡。Web全部检查和123文件1023项测试通过；1440／390五状态、草稿与URL、原生键盘及隐藏字段校验、减少动效、动态高度布局探针和独立审查已核对。首轮并发超时与旧卸载断言另记，最终串行全量零失败／零跳过；模拟证据不升级真实平台能力。见[验收记录](records/2026-10-08-监控工作区GSAP过渡验收.md)。


## 2026-10-09 关键词平台入口与登录弹窗

详见[验收记录](records/2026-10-09-关键词平台入口与登录弹窗.md)。当前Web格式、类型、构建通过；原工作区校验脚本并行删除导致lint及部分配置测试无法运行，隔离副本补入HEAD校验脚本后lint与124文件1032项测试通过。独立审查及桌面/390px真实浏览器公开阅读与弹窗操作通过。docs索引/check通过。真实账号、邮件、OAuth和多平台实采本轮未执行。

追加移除账户入口上方的服务就绪提示及侧栏健康请求；浏览器确认提示消失且登录入口保留。侧栏38项测试、类型检查与118份文档check通过。

本次用户授权提交main：按暂存区导出独立提交树，保留Git中的校验脚本，排除并行首页加载改动与脚本删除。该提交树lint、format:check、typecheck、build及124文件1025项测试通过，118份文档检查通过。首次测试出现进程超时，降至2个worker后全量复跑通过；初次构建软链接越界，改为独立依赖目录后通过。


## 2026-10-10 账户与更多菜单

隔离快照Web检查与1032项测试通过，最终头像语义/分组文案修复后47项回归及构建、lint、类型、格式通过；31组生产浏览器菜单检查与菜单范围axe通过，独立审查通过。共享工作区并行改动与既有脚本删除未覆盖；结果范围、CSS优化警告和复跑证据见[验收记录](records/2026-10-10-账户与更多菜单优化.md)。文档pnpm index及pnpm check通过：122份文档。
