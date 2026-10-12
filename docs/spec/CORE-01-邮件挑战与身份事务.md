# CORE-01 邮件挑战与身份事务

## 业务依据与范围

本切片交付“邮件验证失败可安全恢复，成功仅建立一次本人身份会话”，对应[FR/AC-29-01及边界](../requirement/29-登录与验证注册.md)、[US-29-01](../prd/29-登录与验证注册.md#us-29-01-验证身份并安全进入)、[设计29](../design/29-登录与验证注册.md#邮件挑战物理方案)、[PLAN T-29-01/02/04](../plan/29-登录与验证注册.md#工程任务与完成判据)。本人绑定/改凭据同时覆盖[FR/AC-30-01](../requirement/30-账户与订阅设置.md#ac-30-01-维护身份与安全)、[US-30-01](../prd/30-账户与订阅设置.md#us-30-01-维护身份与安全)及[PLAN T-30-02](../plan/30-账户与订阅设置.md#工程任务与完成判据)，不代表订阅或整个账户模块完成。适用NFR按需求29引用；权限沿用10，不另造业务AC。

覆盖匿名邮件登录/验证注册、本人邮箱绑定、邮件证明修改凭据。现有Redis消费先于PG提交，须完整替换为同一PG事务。密码/GitHub保持各自验证路径；OAuth跨存储事务、恢复后独立删除/撤权屏障、真实SMTP送达和业务库切换属于后续范围，不能以本切片完成替代。

## 就绪条件

- 已有账户/会话唯一约束、CSRF、同源校验和邮件适配器可消费。
- 固定300秒有效期、5次错码上限；发送冷却60秒、邮箱每小时5次、IP发送每小时20次、IP验证每小时60次延续安全边界。这些是工程安全限制，不是产品质量目标。
- 匿名必须有随机浏览器nonce；认证必须有有效owner/session/credential_version，不接受请求正文中的owner身份。
- 独立审查本SPEC及需求/设计映射并解决阻断，然后提交固定规格版本；实施记录版本在BACKLOG。没有已评审SPEC不开始业务代码。
- 只用全新hotkey_test_*库、独立缓存前缀与邮件样本；不改业务库，不发真实SMTP/OAuth，不启动旧业务结构上的新服务。

## 数据合同

唯一邮件挑战真源为`identity_email_challenges`，规范DDL在backend/sql/schema.sql，ORM在identity/models.py。不存明文代码或浏览器nonce。

| 字段 | 类型/可空 | 约束与用途 |
|---|---|---|
| scope_digest | BYTEA/否 | PK；32字节HMAC(normalized email,purpose,binding_digest)，一个验证流只保留最近挑战 |
| challenge_id | UUID/否 | UNIQUE；重发生成新值，旧ID不再可查询 |
| email | VARCHAR(254)/否 | lower+strip规范化；不以casefold错误合并邮箱；用于发信与身份 |
| purpose | VARCHAR(24)/否 | CHECK login/email_link/credentials_update |
| binding_digest | BYTEA/否 | 32字节HMAC；匿名browser nonce；认证owner/session/credential_version |
| code_digest | BYTEA/否 | 32字节HMAC(challenge_id,email,purpose,binding_digest,code)，缺密钥拒绝 |
| attempt_count | INTEGER/否 | CHECK 0..5；错误提交累积，不因错误返回回滚 |
| created_at / expires_at | TIMESTAMPTZ/否 | expires_at>created_at；300秒有效；expires_at索引支持清理 |
| consumed_at / invalidated_at | TIMESTAMPTZ/是 | 终止状态互斥；成功消费或SMTP失败失效 |

不建立伪造匿名owner/FK，认证上下文以不可逆绑定及事务内当前会话检查证明。active转换为consumed/invalidated/attempt-exhausted/expired；后两者由字段推导。过期行可删除，不作长期审计真源；发码/验证按expires_at有界清理，过期拒绝独立于清理运行。空闲物理保留时限及定期清理证据仍为上线生命周期验收项，不声称本切片完成该验收。

## 接口、绑定与安全合同

保留现有HTTP DTO和稳定错误码，完整替换邮件验证码存储协议。匿名发码成功后设置安全随机HttpOnly、SameSite=Lax、生产Secure的nonce Cookie，Path=/api/identity，有效期300秒；携带该Cookie才可兑换。Cookie名为hotkey_email_browser；发码复用浏览器当前合法nonce（43字符base64url），不存在/非法时首次生成，成功发送后刷新300秒Cookie期限，挑战自身期限不延长。浏览器到期丢弃后重新生成即为新流。同浏览器已建立nonce的多标签共享该流；首次无Cookie的并发发码可能各得不同nonce，以浏览器最后收到的Cookie为准，其余挑战安全拒绝并重新申请，不保证两次首次发码均可兑换。Cookie由Router传入领域，不进DTO/OpenAPI、URL或日志。缺失/不同浏览器绑定返回invalid_email_code，禁止省略绑定回退旧协议。

认证发码以服务端AuthenticatedIdentity的owner/session/credential_version构造绑定，绑定邮箱及更新凭据使用不同purpose。写事务内重锁并检查实际账户/会话归属、版本、撤销和期限；旧会话/版本不能改身份。ID/代码使用安全随机源，摘要使用HMAC和常量时间比较；字段篡改不能改变验证目标。Redis不可用或缺密钥返回auth_dependency_unavailable，保持fail closed。

## 事务、并发及恢复合同

1. Redis原子申请发送限流，再以scope_digest唯一键UPSERT最新挑战。UPSERT使并发首次发送及重发串行，不能用不存在行的FOR UPDATE假装互斥。重发替换同一email/purpose/binding流；其他浏览器/用途为独立流。
2. 发码PG提交后在事务外SMTP；失败另开短事务，仅按本次challenge_id失效，不能误伤较新重发。限流不退款，未知邮件效果不自动重发。
3. 验证先申请IP限流，短PG事务内按challenge_id FOR UPDATE；锁后取新的UTC真实时钟，不能以事务开始时now()判断等锁后过期。复验字段、purpose、绑定、摘要、期限和次数。
4. 错码/用途/绑定不符在可用挑战行累积一次错误并提交后再抛invalid_email_code；5次后拒绝正确码。缺失/过期/已消费/已失效均拒绝，不改变身份/会话。
5. 正确码的consumed_at和身份建/绑定、新owner历史、凭据及会话写入同一事务；任一步或提交失败全部回滚，原挑战在当前期限/次数内可重试。业务冲突不退款限流。
6. 固定锁序challenge→user→session。无邮件路径仅user→session，不得反向取challenge锁；发码/失效/清理只锁challenge，不跨网络持锁。等user/session锁后再次取真实时钟检查会话与挑战期限。
7. 并发正确兑换最多一个成功。唯一冲突内部重试必须在新事务重新锁挑战并复验，禁止缓存证明。PG已提交而HTTP丢失仍为consumed，重放不能再建会话；客户端核对已有会话或重新申请挑战。

## 验证矩阵

各场景使用隔离PG、专属Redis前缀、记录邮件样本；角色和业务判据引用AC-29-01，下表只细化工程边界。

| 场景 | 起始条件及操作 | 可观察预期 | 验证层 |
|---|---|---|---|
| 正常三路径 | 浏览器/本人会话发码，正确兑换 | 一次身份写入+会话；绑定/改凭据撤旧会话 | HTTP+PG |
| PG失败恢复 | 正确码后注入身份/会话写或提交失败，再重试 | 首次全回滚且未消费；重试一次成功 | 事务故障注入 |
| 提交响应丢失 | 成功后丢弃响应，再兑换 | 身份/会话存在，重放拒绝，无第二会话 | HTTP/服务 |
| 并发正确兑换 | 同流多连接兑换 | 一个成功，其余拒绝，唯一账户/会话 | 多连接PG |
| 错码/绑定/版本 | 5次错后正确；其他浏览器/用途/会话/版本 | 次数持久化，跨上下文拒绝，身份不变 | HTTP+PG |
| 重发 | 同流新码后兑旧；并发首次/重发 | 最新ID唯一有效，旧ID拒绝 | UPSERT并发 |
| 等锁过期 | 持challenge或user锁至过期再放锁 | 拒绝且无身份/会话写入 | 多连接边界 |
| SMTP失败竞态 | 失败前已存在较新同流挑战 | 只失效失败ID，最新有效 | 样本+PG |
| 篡改/缺密钥 | 改email/purpose/binding或撤密钥 | HMAC拒绝/稳定503，无账户改变 | 集成 |
| Web代理 | 经Web代理发码并带Cookie兑换/重发/异浏览器尝试 | nonce双向转发；同流旧ID及跨浏览器拒绝 | Web代理+HTTP集成 |
| 非法DDL状态 | 新库插入非法摘要/用途/次数/期限/双终态 | 约束拒绝 | SQL断言 |

## 实施、切换与回退

Web代理frontend/src/app/api/[[...path]]/route.ts的请求Cookie及Set-Cookie白名单、frontend/src/request.ts的SSR Cookie白名单必须同步支持hotkey_email_browser；用代理测试验证转发与后端绑定集成，不能只证明后端直连可用。

T-29-01实现表/领域，T-29-02连接事务内身份/会话，T-29-04验证矩阵及AGENTS门禁。先schema/ORM/领域，再服务/HTTP绑定。Redis邮件旧脚本删除，不双写或回退；OAuth脚本不冒充邮件替代物。每个内部重试与异常均复核事务边界。

结构只用于新测试库。业务切换先按PROJECT §6备份/恢复、映射、会话/挑战失效及恢复隔离验证；旧Redis挑战不迁移，重新发码。回退不得激活旧码或撤销前会话；停止兑换、清除未完成挑战并恢复审核过的同事务版本，不直接回退错误提前消费实现。独立恢复屏障SPEC未就绪前不进行业务恢复开放读取。

通过测试/独立审查后在BACKLOG记录SPEC版本、结果、未验证范围及下一缺口，再按授权提交main推送。SPEC不保存完成流水；新冲突先修SPEC及所属设计并重审，不以兼容保留错误语义。
