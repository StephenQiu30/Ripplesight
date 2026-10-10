# Ripplesight 后端

架构与约定见 [PROJECT](../PROJECT.md)，工程规范见 [AGENTS](../AGENTS.md)。

## 本地运行

先在仓库根目录准备 `.env`（复制 `.env.example`），再在 `backend/` 下安装依赖：

```bash
uv sync --locked
```

各进程分别启动，每个命令在单独的终端里执行：

```bash
uv run --locked --env-file ../.env uvicorn main:create_app --factory --app-dir app --host 127.0.0.1 --port 8667 --no-proxy-headers --no-access-log
```

```bash
PYTHONPATH=app uv run --locked --env-file ../.env python -m worker
```

```bash
PYTHONPATH=app uv run --locked --env-file ../.env python -m worker.scheduler
```

```bash
PYTHONPATH=app uv run --locked --env-file ../.env python -m cli --help
```

- API 启动时不会建表，也不会修改数据库结构。
- Worker 在宿主机上运行，因为它需要使用本机的 Codex 登录状态和 MediaCrawler 浏览器。同一时间只运行一个 Worker。
- RSSHub/SearXNG 的主机默认是 `127.0.0.1`，在 Compose 中是 `host.docker.internal`，端口固定为 1200/8888。修改主机后，需要用 CLI 重新应用来源预设。

## 测试

```bash
uv run ruff check .
```

```bash
uv run ruff format --check .
```

```bash
uv run mypy
```

```bash
HOTKEY_TEST_DATABASE_URL=postgresql://USER:PASSWORD@127.0.0.1:5432/hotkey_test_local uv run pytest
```

集成测试需要一个独立的、已用 `schema.sql` 初始化的测试库（名称为 `hotkey_test_<后缀>`）；测试结束后，无论成功还是失败都要删掉它。绝不能指向业务库 `hotkey`。

## 数据库

`sql/schema.sql` 是唯一的建表来源，只能用于全新的空库：

```bash
psql -X --set ON_ERROR_STOP=on --dbname 'postgresql://USER:PASSWORD@HOST:5432/DATABASE' --file sql/schema.sql
```

有数据的库不能直接执行这个脚本，升级流程见 [PROJECT §6](../PROJECT.md#6-数据库)。

## 常用维护命令

| 命令 | 作用 |
|---|---|
| `python -m cli lifecycle cleanup-once --limit 100` | 执行一批到期清理 |
| `python -m cli backup create-candidate --destination <目录>` | 生成数据库与证据文件的备份候选 |
| `python -m cli backup verify-restore --candidate <备份> --isolation-url-env HOTKEY_TEST_DATABASE_URL` | 在临时库中实际恢复并校验 |

以上命令都需要加前缀 `PYTHONPATH=app uv run --env-file ../.env`。

来源凭据只写在根 `.env` 的 `HOTKEY_SOURCE_CREDENTIALS`（JSON 格式），不要出现在命令参数、聊天、Git 或日志里。数据库中只保存凭据的不可逆指纹。
