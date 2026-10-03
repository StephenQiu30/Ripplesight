# HotKey Backend

Python 3.12、FastAPI、Uvicorn、Pydantic 2、SQLAlchemy 2、psycopg 3、PostgreSQL、Redis、Kafka、MinIO。

采用按业务领域分组的模块化单体。项目架构、目录、API 契约和数据库事实源统一执行根目录 [PROJECT.md](../PROJECT.md)；实现门禁和验证命令执行 [AGENTS.md](../AGENTS.md)。

## 执行入口

复制 `.env.example` 为未跟踪的 `.env`，填写数据库凭据并指向业务库 `hotkey`。在 `backend/` 执行 `uv sync --locked`；从 `backend/app/` 执行以下独立入口：

```bash
uv run --locked uvicorn main:create_app --factory --host 127.0.0.1 --port 8667 --no-proxy-headers --no-access-log
uv run --locked python -m worker
uv run --locked python -m cli
```

API、Worker 和 CLI 分别启动。应用启动不会创建或修改数据库结构。

集成测试只使用本机独立 `hotkey_test_<suffix>` 数据库，不能指向业务库；测试执行者负责创建、初始化，并在成功或失败后删除测试库。恢复验证的 `hotkey_restore_*` 临时库由恢复流程清理，不复用 Demo 或历史计划库。

宿主机 Worker 的 `HOTKEY_RSSHUB_HOST/HOTKEY_SEARXNG_HOST` 默认 `127.0.0.1`；根 Compose 默认 `host.docker.internal`。两项仅允许这两个固定主机，RSSHub/SearXNG 端口分别固定 1200/8888；SearXNG 引擎固定 `duckduckgo news`。应用来源预设时将主机与白名单写入连接版本，修改环境后需显式重新应用预设，不会改写已有版本。

浏览器登录状态维护仅适用于数据库中已存在的 `browser_state` 连接；目前尚无真实平台连接创建入口。操作者在本机设置 `HOTKEY_BROWSER_STATE_DIR` 为已存在、权限 0700 的绝对目录，捕获文件必须位于 0700 目录、权限 0600，且不得是符号链接。CLI 不接收 Cookie 正文参数，不打印捕获内容或路径：

```bash
uv run --locked python -m cli connections rotate-browser-state --owner-id OWNER_UUID --connection-id CONNECTION_UUID --expected-version 1 --capture-file /absolute/private/storage-state.json
uv run --locked python -m cli connections disable-browser-state --owner-id OWNER_UUID --connection-id CONNECTION_UUID --expected-version 2
```

停用后需导入新的人工登录状态才能重新启用；未接入平台适配器前，这些命令不代表平台采集可用。

## 数据库结构

[`database/schema.sql`](database/schema.sql) 是唯一 DDL 事实源，维护当前完整表、约束和索引；SQLAlchemy Model 只负责运行时映射，不生成第二套结构。应用、测试、CI、Compose 和备份校验均使用该文件；持久化测试不通过 ORM 或 SQLite 建业务表。每次数据结构变更必须在同一提交中更新 SQL、Model，并用真实 PostgreSQL 核对全部映射表的列、类型、可空性和主键。`datetime` 统一映射为 `TIMESTAMPTZ`。

该文件只允许写入新建空库，并自行包含完整事务边界：

```bash
psql -X --set ON_ERROR_STOP=on \
  --dbname 'postgresql://USER:PASSWORD@HOST:5432/DATABASE' \
  --file database/schema.sql
```

当前不支持对存量数据库自动就地升级。需要保留数据时，先完成备份与恢复演练，再新建数据库、应用完整 `schema.sql` 并导入经过校验的数据；禁止对现有旧库直接执行该文件。

仓库根 `docker-compose.yml` 只编排应用，默认连接已有 PostgreSQL/Redis/Kafka，不启动环境服务。复制根 `.env.example` 为未跟踪的 `.env`，填写完整数据库 URL、Redis URL、Kafka 地址与密钥后，从根目录执行：

```bash
docker compose --env-file .env config --quiet
docker compose --env-file .env up --detach --build --wait
```

生产入口 `docker-compose-prod.yml` 通过 include 复用相同服务定义，使用 `docker compose --env-file .env.prod -f docker-compose-prod.yml up --detach --build --wait`。需要 Compose 2.20.0+；开发与生产的应用镜像、profile、命令和安全限制一致，连接信息与密钥分开注入。

`docker-compose-env.yml` 仅在需要全新环境时显式启动；本地开发默认复用已有环境。它保留原持久卷名，仅在全新 PostgreSQL 空卷通过官方初始化目录运行 `schema.sql`。连接和组合启动方法见[根 README](../README.md#启动服务)。Worker 与 CLI 保留按需 profile；M1/M2 使用宿主机 Worker，受控环境才显式启动容器 Worker。普通停止不删除持久卷，验证直接使用 Compose 与各依赖官方 CLI。

已配置的运行环境可用以下有界命令执行一批到期扫描与 Redis/MinIO 在线副本清理；它不会创建或启动新的依赖服务：

```bash
docker compose run --rm cli lifecycle cleanup-once --limit 100
```

来源凭据只由维护者写入未跟踪的 `backend/.env`（开发 Compose 使用根 `.env`，生产显式使用根 `.env.prod`）中的 `HOTKEY_SOURCE_CREDENTIALS` JSON 映射，键仅允许 `x`、`douyin`，值为对应获授权凭据，默认 `{}`。不要把真实值放入命令参数、聊天、Git 或日志。修改后只替换现有 API/Worker 进程，再从 `/sources` 确认配置或替换；页面不提供秘密输入/回读。数据库只存不可逆指纹引用，移除或替换环境值会使原连接需重新授权。停用不删除历史资料，重新启用产生新版本并重新验证；配置完成不等于获准采集或能力可用。

来源维护者完成一次显式探测后，可在现有环境登记稳定结果：

```bash
uv run --env-file .env python -m cli connections record-probe \
  --owner-id OWNER_UUID \
  --connection-id CONNECTION_UUID \
  --connection-version 1 \
  --operation-id OPERATION_UUID \
  --capability search \
  --entry-point manual \
  --outcome succeeded \
  --component-name approved-probe \
  --component-version 1
```

命令只登记 probe 事实，不读取连接秘密、不发起外部请求，也不会将能力标为可用。`--connection-version` 必须使用探测实际执行的版本，不可在登记时改成新版本；连接停用或版本已变更会拒绝新增证据，已提交的同一事实重放仍返回原记录。失败结果必须另传 `--stop-reason`；只有后续采集用例持久业务记录后才能登记 persisted read 成功。

维护者可在现有本机环境显式指定一个已存在的受控目录，生成 PostgreSQL custom-format 候选归档、MinIO 证据对象内容和引用清单：

```bash
PYTHONPATH=app uv run --env-file .env python -m cli backup create-candidate \
  --destination /absolute/protected/backup-root
```

命令不创建服务、不修改数据库，也不把凭据写入参数或候选包。可在同一 PostgreSQL 服务中，以单独维护库的连接环境变量运行实际恢复验证；MinIO 内容会写到随机临时对象名前缀、回读校验后清理：

```bash
PYTHONPATH=app uv run --env-file .env python -m cli backup verify-restore \
  --candidate /absolute/protected/backup-root/hotkey-backup-... \
  --isolation-url-env HOTKEY_TEST_DATABASE_URL
```

隔离连接不能指向业务库；命令创建并清理唯一临时数据库，核对逐表行数和受控读写，MinIO 对象在同一 bucket 的随机前缀验证内容后清理，输出完整验证耗时。`manifest.json` 保持 `restore_verified=false`；独立介质、删除重放及 B0 RPO/RTO 演练前不能称为完整已验证备份。

业务接口统一使用 `/api` 命名空间，例如存活检查 `/api/health`、就绪检查 `/api/ready`。采集任务使用 `POST /api/jobs` 持久受理，按响应 `Location` 读取 `GET /api/jobs/{job_id}`，并以 `POST /api/jobs/{job_id}/cancel` 登记取消；详情返回持久阶段、已发请求、已保存数量及取消截止。来源处理器的实现与真实验收状态见 [BACKLOG](../BACKLOG.md)，受控 Worker 验证不能代替来源接入验收。接口文档入口为 Swagger UI `/docs`、Scalar `/scalar`，共用 `/openapi.json`。

## 用户登录与数据归属

账号密码、GitHub OAuth App、邮箱验证码共用 `identity/` 的账户与12小时固定数据库会话，业务API读写验证用户UUID及资源归属，写入另校验绑定CSRF。运营令牌和来源平台凭据继续独立管理。首次GitHub/邮箱验证创建个人空分区，密码不自动注册，不把历史分区授给首个注册者。

密码登录支持已验证邮箱或原用户名；邮箱验证后未设置密码的账户进入首次设密，既有账户也可从账户设置完成。首次设密允许5分钟内新近验证会话，超时须重新核验绑定邮箱；已有密码须当前密码或绑定邮箱验证码。凭据更新返回新会话并轮换Cookie，在同事务撤销全部旧会话，当前设备继续登录。此变更不新增数据库字段，运行库无需执行DDL。

配置 `HOTKEY_WEB_ORIGIN`、GitHub OAuth App client ID/secret、认证SMTP及邮箱验证码HMAC key；真实密钥只留本机环境文件。GitHub缺失配置时明确不可用；邮箱6位码5分钟、单次且错误/频率受限，不记录明文。数据库Schema只在新空库验证，存量库备份/恢复/导入核对后切换；历史账号归属必须用维护CLI显式映射。HTTP/Cookie/API合同见 [Design001 §9.2](../docs/design/001-热点舆情监控平台总体设计.md#92-公开欢迎页登录与个人数据访问)。

来源/模型秘密不得进入Git、日志、前端或模型输入；ToC账户不改变来源许可证与授权边界。MediaCrawler仍保留个人、非商业研究及本人B站低频试点限制。

## 状态

当前实现与逐能力证据分别见 [BACKLOG](../BACKLOG.md) 和 [Acceptance 索引](../docs/README.md)，历史底座盘点从 Git 历史查阅。服务健康、受控适配器及技术门禁不能替代真实来源或产品验收。
