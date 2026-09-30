---
layer: Plan
scope: issue
doc_no: "060"
title: GitHub与邮箱验证码登录执行计划
status: planned
version: v1.0
date: 2026-10-01
owner: HotKey Team
canonical_path: docs/plan/060-GitHub与邮箱验证码登录执行计划.md
prd: docs/prd/001-热点舆情监控平台需求.md
design: docs/design/001-热点舆情监控平台总体设计.md
source_task: 用户2026-10-01明确的ToC账户与身份设计清理
architecture_prerequisite: "046 S03"
depends_on: ["051", "056"]
---

# Plan060：GitHub、邮箱验证码与既有密码登录及会话恢复

## 1. 范围与依赖

承接 FR-001-122—128、AC-001-123—129、NFR-001-113 与 DEC-001-226。按2026-10-01用户最新补充，保留用户名、密码及用户名密码登录，增加 GitHub App 与邮箱验证码，无感登录为必要能力。首次 GitHub/邮箱验证即注册；密码登录只校验已有账户。取消部署密钥、单账户限制与重复工作区身份接口，复用服务端会话、密码哈希/凭据版本和资源归属规则，不新增组织、租户、角色、邀请或通用认证框架。

本轮仅形成设计与文档，未改应用、配置、Schema、客户端或运行环境。本卡 `planned`，所有 Checklist 未执行。当前旧登录仍在运行；不通过删除密钥校验把旧初始化接口变为无授权的开放入口。

历史046 S03真实门槛见 Design001 §5，HTTP变更回归由056维护。新Schema在隔离空库验证；保留运行数据的切换需051同版本备份/恢复证据。真实GitHub步骤需要App注册、用户只读邮箱权限和回调地址；真实邮件步骤需要SMTP与发件地址。缺少集成配置只阻塞相应真实验收，不以受控HTTP/SMTP或截图冒充真实成功。

## 2. 文件与职责

| 分类 | 路径 | 职责 |
|---|---|---|
| 修改 | `backend/app/identity/{models,schemas,services}.py`、`backend/database/schema.sql` | 用户/会话、验证身份查找或创建、登录/凭据事务与撤销；保留用户名、密码哈希和凭据版本，删除单账户约束、部署初始化及workspace包装 |
| 新增 | `backend/app/identity/adapters/{__init__,github,email,verification_store}.py` | HTTPX GitHub授权/用户读取、标准库SMTP、Redis临时挑战与原子限流；不得依赖API、Worker或其他业务ORM |
| 修改 | `backend/app/api/routers/identity.py`、`api/dependencies.py`、`api/exception_handlers.py`、`core/{config,errors}.py`、`main.py`、`backend/Dockerfile` | 类型化端点、错误登记、资源装配/释放、服务端配置与客户端真实IP校验；Uvicorn关闭自动代理头改写，保留真实TCP peer用于信任判断 |
| 修改 | `backend/app/cli/{commands,jobs}.py` | 保留reset-password并要求--user-id，移除initialized_owner_id默认取首用户；所有用户范围维护命令显式选用户 |
| 修改 | `backend/app/backups/restore.py` | 导入保留用户名/密码哈希/凭据版本并补经核对的邮箱；隔离恢复探针回滚且不暴露凭据 |
| 修改 | `backend/app/worker/scheduler.py`、`worker/app.py` | 核对多用户主题扫描、Job/连接/预算归属及装配；不扩大采集/模型权限或并发 |
| 修改 | `backend/pyproject.toml`、`backend/uv.lock`、`.env.example`、`backend/.env.example`、`docker-compose.yml` | 删除bootstrap配置，保留pwdlib[argon2]；通过uv维护Pydantic邮箱验证依赖，注入GitHub/SMTP/验证码摘要配置；模板只放空值与说明 |
| 修改 | `frontend/src/app/login/{page.tsx,components/login-form.tsx}`、`app/register/page.tsx`、`components/auth/{auth-shell,credentials-fields}.tsx` | 保留用户名密码与PasswordField，增加两种验证方式；登录页先恢复会话，有效直接跳转，旧register重定向 |
| 新增 | `frontend/src/app/login/components/{github-login-button,email-code-form}.tsx` | 登录页专属组件，状态由生成身份API提供，不提前迁入公共组件 |
| 新增 | `frontend/src/app/account/{page.tsx,components/account-form.tsx}` | 已登录用户设置用户名/密码与恢复流程；复用CredentialsFields，当前身份邮箱只读，验证码绑定凭据更新用途 |
| 删除 | `frontend/src/app/register/components/register-form.tsx` | 仅移除旧部署密钥初始化表单 |
| 修改/生成 | `frontend/src/{request.ts,api/}`、`app/events/components/events-workspace.tsx`、`app/monitors/new/components/topic-form.tsx` | CSRF公开路径、运行OpenAPI生成、session读取/用户名邮箱展示与账户入口；不手改生成类型 |
| 修改 | `frontend/src/app/api/[[...path]]/{route,route.test}.ts` | 传递受控入口覆写的单值客户端IP；回调303/Location/多个Set-Cookie透传，15秒代理截止与身份请求截止协调 |
| 修改 | `.github/workflows/{backend,contract,runtime}.yml`、README/PROJECT/AGENTS/进度索引 | 替换CI旧部署初始化，保留密码登录回归；受控新通道只作CI验证，runtime核对两用户与Cookie自动恢复/脱敏 |
| 测试 | `backend/tests/unit/{test_application_security,test_account_tracking,test_collection_job_contract}.py`、`backend/tests/conftest.py`、`backend/tests/integration/{test_http_contract,test_http_contract_046}.py`；其他集成文件清单见下文 | 新认证、真实双账户、跨用户/会话/恢复与业务回归；逐一替换旧初始化夹具和直接旧字段构造，不留测试专用绕过认证端点 |
| 新增测试 | `backend/tests/unit/test_identity_login_contract.py`、`backend/tests/integration/test_identity_login.py`、`frontend/src/app/login/components/{email-code-form,github-login-button,login-form}.test.tsx`、`frontend/src/app/account/components/account-form.test.tsx` | 新契约、Redis单次消费/并发、唯一身份、密码维护、会话自动恢复与失败状态 |

实施前用 `rg` 补齐实际旧字段调用与夹具清单，并在同一切片修正。登录适配器只封装外部差异，identity服务拥有用户与会话事务；不跨网络请求持有SQLAlchemy事务，不以共享层聚合其他业务。

现有集成夹具清单均位于 `backend/tests/integration/`：`test_ai_calls.py`、`test_analysis_annotations.py`、`test_analysis_pipeline.py`、`test_application_security.py`、`test_backup_restore.py`、`test_collection_coverage.py`、`test_collection_coverage_http.py`、`test_collection_jobs.py`、`test_content_collection_facts.py`、`test_content_records.py`、`test_coverage_metrics.py`、`test_data_lifecycle.py`、`test_event_clustering.py`、`test_followed_accounts.py`、`test_google_news_replay.py`、`test_hackernews_replay.py`、`test_hotlist_due_scheduler.py`、`test_hotlist_persistence.py`、`test_hotlist_queries.py`、`test_incremental_windows.py`、`test_job_reliability.py`、`test_keyword_discovery.py`、`test_mediacrawler_evidence.py`、`test_monitor_topics.py`、`test_news_search_replay.py`、`test_operational_observability.py`、`test_provenance_replay.py`、`test_resource_budgets.py`、`test_resource_isolation.py`、`test_source_connections.py`、`test_topic_runs.py`、`test_webpage_persistence.py`。这批主要替换真实用户夹具，不新增逐文件镜像测试；实施前再次搜索旧字段、路径与初始化助手补齐漂移。

## 3. 接口与数据合同

所有路径以 `/api/identity` 为前缀。普通输出为Pydantic模型，错误为ErrorView，响应均`Cache-Control: no-store`。未登录POST要求既有`X-HotKey-CSRF: 1`门槛；已登录凭据更新/验证码与注销使用会话绑定CSRF。GitHub回调依赖state和流程Cookie，不以固定CSRF头代替OAuth校验。

OAuth授权URL允许协议所需的state/challenge；verifier、访问令牌和验证码不得进入API响应。Uvicorn关闭原始URL访问日志，沿用应用路由模板日志；受控部署入口同样不得保存回调query或身份请求body。

| 方法/路径 | operation_id | 输入与输出 | 实际状态 |
|---|---|---|---|
| GET `/login-options` | `getIdentityLoginOptions` | 无输入；`{password_enabled:true,github_enabled,email_enabled}`，不回显配置缺失字段或秘密 | 200/500 |
| POST `/sessions` | `createIdentitySession` | 保留严格`{username,password}`；200 `{user:{id,username,email},expires_at}`并设置Cookie，不自动注册 | 200；401/403/422/429/503/500 |
| GET `/github/authorize` | `startGitHubLogin` | 无用户指定URL；`{authorization_url}`并设置5分钟流程Cookie | 200；429/503/500 |
| GET `/github/callback` | `completeGitHubLogin` | 有界code/state或GitHub取消参数；校验后设置会话Cookie，成功303到固定`/events` | 成功/可识别取消失败303到固定`/login?error=安全错误码`；畸形输入422，错误无敏感回显。OpenAPI声明303/Location与空body，不生成假JSON DTO |
| POST `/email/code` | `sendEmailLoginCode` | 判别联合输入：`{purpose:"login",email}`（≤254字符），或会话+CSRF下`{purpose:"credentials_update"}`（邮箱和用户从会话派生）；200 `{challenge_id,expires_at,resend_after_seconds}`，不返回code/账户是否存在 | 200；401仅凭据用途/403/422/429/503/500 |
| POST `/email/session` | `verifyEmailLoginCode` | 严格`{challenge_id,code}`，code精确6位数字且用途为login；200 `{user:{id,username,email},expires_at}`并设置Cookie | 200；401/403/422/429/503/500 |
| PUT `/credentials` | `updateIdentityCredentials` | 会话+CSRF；严格`{username,password,challenge_id,code}`，凭据用途/用户/邮箱相符后更新并撤销全部旧会话、清Cookie | 204；401/403/409用户名占用/422/429/503/500 |
| GET `/session` | `getIdentitySession` | 会话Cookie；`{user:{id,username,email},expires_at}` | 200；401/422/500 |
| DELETE `/session` | `deleteIdentitySession` | 会话Cookie+CSRF；撤销当前会话，清Cookie，无body | 204；401/403/422/500 |

仅删除`POST /initialize`、`GET /workspace`及专属DTO/错误/客户端；保留密码`POST /sessions`及其契约。回调重定向只带安全错误码，不带邮箱、令牌、code或state；页面按码提供重试与请求错误提示。忘记密码先通过邮箱验证码登录，再到/account执行凭据更新，复用同一账户和验证码服务，不另设部署者恢复身份。

| SPEC | 固定合同 |
|---|---|
| SPEC-060-USER-001 | users保留UUID、唯一username、password_hash和credential_version，新增唯一规范email与可空唯一GitHub ID；无密码的新通道用户hash可空，不生成假密码，默认username为user_加UUID.hex。username沿用3—64字符小写ASCII字母数字及._-，旧用户名保留。sessions保留FK、token/CSRF摘要、凭据版本、时间/撤销，只删除singleton_key。GitHub ID先匹配，首次按已验证主邮箱关联，另一GitHub ID冲突拒绝；邮箱小写trim不合并点/+别名，唯一约束处理并发，账户+会话同事务提交。 |
| SPEC-060-PASSWORD-001 | 保留pwdlib[argon2]、12—128字符密码、哈希自动升级与未知用户dummy校验；无密码/未知用户/错误密码统一invalid_credentials。密码登录每username+可信IP组合15分钟最多5次失败、每IP每小时60次尝试，限流429/Retry-After、Redis不可用503，不对所有用户作全局账号锁定。凭据更新须会话/CSRF+5分钟单次credentials_update验证码，原子改username/hash、递增用户版本、撤销全部旧会话；会话认证比较版本，不回显密码/哈希。CLI保留reset-password --user-id与隐藏输入/确认，不取首用户。 |
| SPEC-060-GH-001 | GitHub App用户Web授权：32字节随机state、PKCE S256、固定回调；Redis保存state摘要、verifier与5分钟有效期，流程HttpOnly/Lax Cookie与回调state一致后原子消费。HTTPX限定GitHub官方授权/token/user/emails端点，不跟随任意重定向；所有外部步骤共用10秒截止，身份整请求最多12秒，保留Next现有15秒截止的余量。只读Email addresses，不需安装、App私钥或仓库权限；访问token仅在本次后端请求中使用。验证失败不落用户或会话。 |
| SPEC-060-OTP-001 | 6位随机验证码、随机challenge ID，HMAC绑定email/ID/code/purpose及凭据用途的用户UUID，Redis TTL300秒；login与credentials_update不能互换，凭据用途从会话派生用户/邮箱。单次原子消费、最多5次失败，同邮箱+用途重发成功作废前挑战；冷却/额度跨用途共用，每邮箱60秒/5次每小时，每IP发送20次/校验60次每小时。限流429/Retry-After，错误/过期统一invalid_email_code，Redis失败503，不暴露账户是否存在。 |
| SPEC-060-MAIL-001 | 同步身份SMTP适配器，TLS证书验证，发件地址/主机/凭据只从服务器配置读；禁CRLF，固定短文本邮件含用途、验证码和5分钟时限。网络调用在数据库事务外，总截止10秒。SMTP失败/超时/未知时失效新挑战、返回email_delivery_unavailable、不自动重发；已经注册与未注册邮箱表现一致。受控SMTP证明协议，真实收件证明送达。 |
| SPEC-060-SESSION-001 | 不透明Cookie与数据库SHA-256摘要，三种登录共用；默认12小时固定过期，Max-Age一致，可多会话；Strict/HttpOnly、生产Secure、注销当前会话、绑定CSRF与凭据版本。页面/浏览器重开自动读取/session，有效则恢复，/login先检查有效会话跳/events；仅401进入登录，网络/服务失败提供重试不误清Cookie。退出/过期/撤销/密码变化要求重新验证，不存客户端密码/令牌，不加JWT/refresh/滑动续期。OAuth临时Cookie独立Lax并回调清除。 |
| SPEC-060-ISOLATION-001 | 会话提供actor UUID，资源归属字段仍可名为owner_id但不构成owner角色。所有列表/详情/写入/导出及Job、来源、内容、预算按用户过滤；CLI显式--user-id，调度扫描全部有效主题，不取第一个账户。隔离库必须真正创建两用户及各自数据，不能替换依赖伪装第二用户。恢复探针和同版本导入满足新表。 |
| SPEC-060-CONFIG-001 | 新字段HOTKEY_PUBLIC_ORIGIN、HOTKEY_GITHUB_CLIENT_ID/CLIENT_SECRET、HOTKEY_EMAIL_CODE_HMAC_KEY、HOTKEY_AUTH_SMTP_HOST/PORT/TLS_MODE/USERNAME/PASSWORD/FROM、HOTKEY_AUTH_TRUSTED_PROXY_NETWORKS；TLS_MODE仅ssl/starttls，密钥均SecretStr，摘要密钥≥32字节。可信代理配置仅接受实际Web到API的IPv4/IPv6 CIDR，拒绝0.0.0.0/0与::/0。公开Origin必须固定，生产HTTPS，回调由Origin派生。缺通道配置不展示假可用；配置半套拒绝启动。复用会话/Redis配置；不需要部署密钥、用户白名单或GitHub App私钥。 |
| SPEC-060-PROXY-001 | 公开请求固定“受控部署入口→Next→API”：入口删除来访者的X-Real-IP/Forwarded/X-Forwarded-*，用实际TCP客户端地址覆写单值X-Real-IP；Web仅接该入口，API仅接Web内网和受控本机维护入口，禁止绕过入口公开访问。Next不转发来访XFF，只传该单值X-Real-IP。Uvicorn关闭自动代理头改写；backend仅在真实TCP peer属于配置可信代理CIDR时读取该头，缺失、多值或非IP时身份请求503；非代理直连API使用TCP peer并忽略所有自报头。本地Web联验也使用受控入口，不以Next地址限流或盲信浏览器头。两客户端/伪造头和绕入口拒绝验证留证；身份整请求12秒、Next15秒，日志不保存邮箱、IP、code/state、Cookie或秘密原文。 |
| SPEC-060-UI-001 | /login保留用户名密码并增加GitHub/邮箱验证码，首次GitHub/邮箱验证注册，/register重定向；LoginForm/AuthShell/CredentialsFields/PasswordField及密码显隐保留，新通道组件留路由目录。/account用户自行设用户名/密码，忘记密码链接引导邮箱验证恢复后到该页；字段错误/用户名占用/验证用途与会话变化可恢复。覆盖自动会话恢复、通道缺失、冷却/错误/过期/限流/取消/网络失败，保留CSP/no-store/noindex/桌面390px/键盘操作。 |

## 4. 旧数据与运行切换

本轮不执行迁移。实现切换前提供旧UUID→已核对邮箱映射，不按username猜邮箱或把旧数据交首个新登录者；保留UUID、username、password_hash和credential_version，不重置既有密码。沿051备份恢复、新库完整Schema、导入/行数/外键/连接/Job/Outbox/预算核对，旧会话不导入、旧库可回退。无可靠映射只能新空库验证，不切换原库。

开发夹具/CI改为真实多用户结构，保留密码登录回归，受控GitHub/SMTP替身只注入测试应用，不在生产API提供跳过验证入口。验收记录放`docs/acceptance/001-共享运行门槛验收.md`，旧单用户证据保留原始含义。

## 5. Checklist、验证与完成条件

- [ ] CHK-060-101：新接口/用户结构、三种登录与仅旧初始化/workspace删除的失败用例；用户名唯一、无密码用户、密码哈希/升级/错误限流、验证邮箱/GitHub ID冲突/并发注册与绑定规则。
- [ ] CHK-060-102：空PG唯一Schema、真实Redis过期/冷却/额度/5次失败/单次消费/并发/重发/故障拒绝；跨用途和跨用户验证码拒绝、凭据更新与并发旧会话失效、新会话/唯一用户事务通过。
- [ ] CHK-060-103：GitHub受控HTTP验证state/浏览器绑定/PKCE/错误/取消/缺已验证主邮箱/超时；受控SMTP验证TLS、头注入、发送失败与未知结果。令牌/验证码及原始邮件不入日志或响应。
- [ ] CHK-060-104：两个真实隔离账户、两组主题/连接/内容/任务/预算证明互不可读写；核对CLI、调度、Worker、恢复探针及同版本导入，补齐所有旧身份夹具。
- [ ] CHK-060-105：后端Ruff/format/mypy/pytest与架构、OpenAPI→生成客户端无漂移；前端test/lint/typecheck/format/build；CI替换bootstrap而保留密码回归，303/Location/多Set-Cookie/近截止/CSRF/脱敏/用户隔离通过。
- [ ] CHK-060-106：真实GitHub与邮件收取/验证码、同邮箱同用户、设用户名密码/密码登录/忘记密码恢复；刷新/重开浏览器及/login有效Cookie无感跳转，退出/过期/密码变化拒绝旧会话、网络失败重试；两用户隔离、桌面390px/可信IP伪造头/生产CSP留证。
- [ ] CHK-060-107：同步README/PROJECT/AGENTS/索引/Acceptance，确认无部署初始化/workspace/单账户假设，用户名密码及自动会话恢复保留；旧库切换另留051同版本证据，配置日志无真实秘密。

技术验证、真实GitHub登录、真实邮件收取、密码/无感用户流程与旧库切换分别记录，全部适用Checklist通过才completed；受控响应或文档不关闭AC-001-123—129。M1来源/模型/连续运行AC独立，不因用户体系重设计自动通过。
